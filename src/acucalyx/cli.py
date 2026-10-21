"""
AcuCalyx CLI: Headless Clinical Decision Support Planning Interface

Command-line entrypoint for batch and automated preoperative planning:
    acucalyx plan --input /path/to/ct_series --output /path/to/case_dir --side left
    acucalyx qc --dicom-dir /path/to/dicom_series
    acucalyx server --host 0.0.0.0 --port 8000
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from acucalyx.pipeline import run_planning_pipeline, PlanningPipelineResult


def setup_logger(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    )


def print_banner():
    banner = r"""
 =====================================================================
      _               ____      _             ____  _ 
     / \   ___ _   _ / ___|__ _| |_   ___  __|___ /| |
    / _ \ / __| | | | |   / _` | | | | \ \/ /  |_ \| |
   / ___ \ (__| |_| | |__| (_| | | |_| |>  <  ___) |_|
  /_/   \_\___|\__,_|\____\__,_|_|\__, /_/\_\|____/(_)
                                  |___/               
    AcuCalyx™ v2.1 — Clinical Decision Support for PCNL
    * Non-Sterile Computer-Assisted Preoperative Planning *
 =====================================================================
"""
    print(banner)


def handle_plan(args):
    setup_logger(args.verbose)
    print_banner()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[ERROR] Input path does not exist: {input_path}", file=sys.stderr)
        sys.exit(2)

    cfg = {}
    if args.config:
        cfg_path = Path(args.config)
        if not cfg_path.is_file():
            print(f"[ERROR] Config file not found: {cfg_path}", file=sys.stderr)
            sys.exit(2)
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

    if args.allow_marginal:
        cfg["allow_marginal"] = True

    print(f"[*] Input Data  : {input_path}")
    print(f"[*] Target Side : {args.side.upper()} Kidney")
    print(f"[*] Output Dir  : {args.output}")
    print(f"[*] Running automated multi-objective planning pipeline...\n")

    try:
        result = run_planning_pipeline(
            input_path=input_path,
            output_dir=args.output,
            side=args.side,
            config=cfg
        )
    except Exception as e:
        logging.exception("Fatal error during planning pipeline execution")
        print(f"\n[FATAL ERROR] {e}", file=sys.stderr)
        sys.exit(2)

    # Display Clinical Summary
    print("\n" + "=" * 70)
    print("                      ACUCALYX CLINICAL SUMMARY")
    print("=" * 70)
    print(f" Case Identifier       : {result.case_id}")
    print(f" Software Version      : {result.provenance.software_version}")
    print(f" Quality Gate Status   : {'PASSED' if result.quality_gate.passed else 'REJECTED'}")
    print(f" PCS Visibility State  : {result.pcs_visibility.state.value} (Conf: {result.pcs_visibility.confidence_score*100:.0f}%)")
    print(f" Collecting System Note: {result.pcs_visibility.clinical_notice}")
    print(f" Detected Calculi      : {len(result.stones)} stone(s)")

    for i, s in enumerate(result.stones):
        att = result.attenuations[i] if i < len(result.attenuations) else None
        hu_str = f"Mean HU: {att.mean_hu:.0f} | Peak HU: {att.peak_hu:.0f}" if att else "HU: N/A"
        print(f"   - Stone #{s.stone_id}: Vol = {s.volume_mm3:.1f} mm³ | Feret Max = {s.max_feret_diameter_mm:.1f} mm | {hu_str}")

    print("\n" + "-" * 70)
    print("                PARETO ACCESS TRAJECTORY CANDIDATES")
    print("-" * 70)
    if not result.candidates:
        print(" [!] No feasible Pareto candidates generated.")
    else:
        for idx, c in enumerate(result.candidates[:3]):
            badge = "[PREFERRED]" if idx == 0 and c.min_effective_clearance_mm > 10.0 else "[CONDITIONAL]"
            print(f" Candidate {chr(65+idx)} ({c.candidate_id}) {badge}:")
            print(f"   Target Calyx      : {c.target_calyx_name}")
            print(f"   Skin Entry LPS    : [{c.entry_point_lps[0]:.1f}, {c.entry_point_lps[1]:.1f}, {c.entry_point_lps[2]:.1f}] mm ({c.access_rib_classification})")
            print(f"   Tract Depth       : {c.tract_length_mm:.1f} mm")
            print(f"   Min Eff Clearance : {c.min_effective_clearance_mm:.1f} mm")
            print(f"   Stone Reachability: {c.reachable_stone_fraction * 100:.1f}%")
            print(f"   Deflection Req    : {c.required_scope_deflection_deg:.1f}°")

            mc_list = result.monte_carlo_assessments.get(c.candidate_id, [])
            for mc in mc_list:
                print(f"   MC Risk ({mc.hazard_name}): P(collision) = {mc.collision_probability*100:.1f}% | 95% worst-case = {mc.percentile_5th_clearance_mm:.1f} mm [{mc.risk_category}]")
            print()

    print("=" * 70)
    print("                     GENERATED CASE ARTIFACTS")
    print("=" * 70)
    out_dir = Path(args.output)
    if result.report_pdf_path and result.report_pdf_path.is_file():
        print(f" [+] Preop Planning Report PDF : {result.report_pdf_path.resolve()}")
    print(f" [+] Case JSON Manifests       : {out_dir / 'quality.json'}, {out_dir / 'candidates.json'}")
    print(f" [+] SHA-256 Provenance Audit  : {out_dir / 'provenance.json'}")
    print(f" [+] 3D Surgical Meshes (GLB)  : {len(result.mesh_exports)} models in {out_dir / 'meshes'}")
    print("\nDISCLAIMER: For clinical decision support only. Non-sterile display.")
    print("=" * 70)

    if result.status == "GATE_REJECTED":
        sys.exit(1)
    sys.exit(0)


def handle_qc(args):
    setup_logger(args.verbose)
    print_banner()

    target = Path(args.dicom_dir or args.input)
    if not target.exists():
        print(f"[ERROR] Target path does not exist: {target}", file=sys.stderr)
        sys.exit(2)

    print(f"[*] Running Imaging Quality Gate on: {target}")
    if target.is_dir():
        from acucalyx.ingestion.dicom import load_dicom_series
        res = load_dicom_series(target)
        qg = res.quality_gate
    else:
        from acucalyx.ingestion.nifti import load_research_nifti
        res = load_research_nifti(target)
        qg = res.quality_gate

    print(f" Quality Gate Status  : {'PASSED' if qg.passed else 'REJECTED'}")
    print(f" Overall Quality Tier : {qg.overall_quality_tier}")
    print(f" Geometry Score       : {qg.geometry_score:.2f} / 1.00")
    print(f" Resolution Score     : {qg.resolution_score:.2f} / 1.00")
    print(f" Slice Spacing        : {qg.slice_spacing_mm:.2f} mm")
    print(f" Slice Thickness      : {qg.slice_thickness_mm:.2f} mm")
    print(f" Pixel Spacing        : {qg.pixel_spacing_mm[0]:.2f} x {qg.pixel_spacing_mm[1]:.2f} mm")
    if qg.rejection_reasons:
        print("\n [!] Rejection Reasons:")
        for r in qg.rejection_reasons:
            print(f"     - {r}")
    if qg.warnings:
        print("\n [!] Warnings:")
        for w in qg.warnings:
            print(f"     - {w}")

    sys.exit(0 if qg.passed else 1)


def handle_server(args):
    print_banner()
    print(f"[*] Launching AcuCalyx Medical Server on {args.host}:{args.port}...")
    import uvicorn
    uvicorn.run("app.api.main:app", host=args.host, port=args.port, reload=args.reload)


def main():
    # If legacy flags (-i/--input, -o/--output) are passed without subcommand, adapt to plan
    raw_args = sys.argv[1:]
    subcommands = {"plan", "qc", "server"}
    if raw_args and raw_args[0] not in subcommands and not raw_args[0].startswith("-h") and not raw_args[0] == "--help":
        if "-i" in raw_args or "--input" in raw_args:
            raw_args = ["plan"] + raw_args

    parser = argparse.ArgumentParser(
        prog="acucalyx",
        description="AcuCalyx™ v2.1 — Clinical Decision Support & Preoperative Planning for PCNL"
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # Plan subcommand
    plan_parser = subparsers.add_parser("plan", help="Execute multi-objective preoperative planning pipeline")
    plan_parser.add_argument("-i", "--input", required=True, help="Path to clinical DICOM directory or research NIfTI volume (.nii, .nii.gz)")
    plan_parser.add_argument("-o", "--output", required=True, help="Target directory for case outputs (JSON, PDF report, 3D GLB/STL meshes)")
    plan_parser.add_argument("-s", "--side", choices=["left", "right"], default="left", help="Target kidney side (default: left)")
    plan_parser.add_argument("-c", "--config", help="Path to JSON configuration file for parameter overrides")
    plan_parser.add_argument("--allow-marginal", action="store_true", help="Allow computation even if DICOM quality gate indicates marginal slice spacing")
    plan_parser.add_argument("-v", "--verbose", action="store_true", help="Enable detailed debug logging")

    # QC subcommand
    qc_parser = subparsers.add_parser("qc", help="Verify DICOM / NIfTI geometric integrity & quality gate")
    qc_parser.add_argument("--dicom-dir", "-d", help="Path to DICOM directory")
    qc_parser.add_argument("--input", "-i", help="Path to DICOM directory or NIfTI file")
    qc_parser.add_argument("-v", "--verbose", action="store_true", help="Enable detailed debug logging")

    # Server subcommand
    srv_parser = subparsers.add_parser("server", help="Launch the AcuCalyx FastAPI clinical web server")
    srv_parser.add_argument("--host", default="0.0.0.0", help="Host interface (default: 0.0.0.0)")
    srv_parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    srv_parser.add_argument("--reload", action="store_true", help="Enable live auto-reloading")

    args = parser.parse_args(raw_args)

    if args.subcommand == "plan":
        handle_plan(args)
    elif args.subcommand == "qc":
        handle_qc(args)
    elif args.subcommand == "server":
        handle_server(args)
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
