"""
AcuCalyx Ultrasound: Physics-Informed Simulated B-Mode Engine
Governed by Milestone M14B of ACU-M14-EXEC-PLAN-2026-V2.

Provides:
1. Sector & linear ray tracing through CT volume / acoustic media.
2. Two-way attenuation with calibrated ln(10)/10 scaling.
3. Posterior acoustic shadow cones distal to calculi and cortical ribs.
4. Distal acoustic enhancement distal to fluid-filled calyces.
5. Lateral beam profile spreading and depth-dependent TGC amplifier.
6. Rayleigh-distributed speckle synthesis.
7. Logarithmic dynamic range compression (60-80 dB -> 8-bit display).
8. Synthetic needle shaft and tip echo overlay.
"""

from dataclasses import dataclass
import io
import math
from typing import Optional, Tuple
import numpy as np
from PIL import Image

from acucalyx.ultrasound.acoustic_properties import (
    classify_ct_voxel_to_acoustic_medium,
    compute_two_way_attenuation_intensity,
    compute_boundary_reflection,
    LN10_DIV_10,
    AcousticTissueClass,
)
from acucalyx.ultrasound.probe_profile import (
    TransducerProfile,
    UltrasoundProbePose,
    CURVILINEAR_C5_2,
    TransducerType,
)
from acucalyx.ultrasound.needle_ultrasound import calculate_needle_acoustic_visibility


@dataclass
class BModeSimulationResult:
    """Output container for synthetic B-mode simulation."""
    image_uint8: np.ndarray  # 2D array (H, W) in [0, 255]
    depth_axis_mm: np.ndarray
    lateral_angles_deg: np.ndarray
    probe_id: str
    stone_shadow_detected: bool
    fluid_enhancement_detected: bool
    needle_rendered: bool
    mean_echogenicity: float

    def to_png_bytes(self) -> bytes:
        """Encodes simulated 8-bit B-mode image as PNG byte stream."""
        img = Image.fromarray(self.image_uint8, mode="L")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


# Alias
SimulatedBModeImage = BModeSimulationResult


class BModeUltrasoundSimulator:
    """
    Physics-informed B-mode ultrasound simulator operating on 3D CT volumes
    or synthetic anatomical representations.
    """

    def __init__(
        self,
        probe: TransducerProfile = CURVILINEAR_C5_2,
        dynamic_range_db: float = 65.0,
        compression_gamma: float = 15.0,
        random_seed: Optional[int] = 42,
    ):
        self.probe = probe
        self.dynamic_range_db = dynamic_range_db
        self.compression_gamma = compression_gamma
        self.rng = np.random.default_rng(random_seed)

    def simulate_from_ct_volume(
        self,
        ct_volume: np.ndarray,
        voxel_spacing_mm: Tuple[float, float, float],
        volume_origin_mm: Tuple[float, float, float],
        probe_pose: UltrasoundProbePose,
        needle_trajectory: Optional[Tuple[np.ndarray, np.ndarray, float]] = None,
    ) -> BModeSimulationResult:
        """
        Traces acoustic rays through CT volume, accumulating backscatter,
        two-way attenuation, shadow cones, TGC, and speckle.
        
        ct_volume: 3D numpy array (Z, Y, X) of Hounsfield Units.
        voxel_spacing_mm: (dz, dy, dx) in mm.
        volume_origin_mm: (oz, oy, ox) in mm.
        probe_pose: UltrasoundProbePose in world LPS coordinates.
        needle_trajectory: Optional tuple (entry_pt, target_pt, insertion_depth_mm).
        """
        dz, dy, dx = voxel_spacing_mm
        oz, oy, ox = volume_origin_mm
        dim_z, dim_y, dim_x = ct_volume.shape

        n_lines = self.probe.num_scanlines
        n_depths = self.probe.num_depth_samples
        max_depth = self.probe.max_imaging_depth_mm
        freq_mhz = self.probe.center_frequency_mhz
        focal_depth = self.probe.default_focal_depth_mm

        depth_steps = np.linspace(0.0, max_depth, n_depths)
        step_ds_cm = (max_depth / n_depths) * 0.1  # Convert mm to cm

        scanline_rays = probe_pose.sample_scanline_rays(self.probe)

        # Raw acoustic radio-frequency / envelope matrix (n_depths, n_lines)
        envelope_matrix = np.zeros((n_depths, n_lines), dtype=np.float32)

        stone_shadow_found = False
        fluid_enhancement_found = False

        # Nominal tissue attenuation rate for TGC compensation (0.5 dB/(cm*MHz))
        nominal_alpha_db = 0.54

        for col_idx, (ray_orig, ray_dir) in enumerate(scanline_rays):
            cum_attenuation_db = 0.0
            beam_extinguished = False

            for row_idx, depth_mm in enumerate(depth_steps):
                if depth_mm <= 0.0:
                    continue

                # 3D world position along ray
                world_pt = ray_orig + depth_mm * ray_dir
                pz, py, px = world_pt[2], world_pt[1], world_pt[0]

                # Convert to voxel index
                vz = int(round((pz - oz) / dz))
                vy = int(round((py - oy) / dy))
                vx = int(round((px - ox) / dx))

                # Check bounds
                if 0 <= vz < dim_z and 0 <= vy < dim_y and 0 <= vx < dim_x:
                    hu = float(ct_volume[vz, vy, vx])
                else:
                    # Outside volume - assume fat/soft tissue boundary
                    hu = -100.0

                medium = classify_ct_voxel_to_acoustic_medium(hu)

                # Beam width spreading factor
                # w(z) = w0 * sqrt(1 + ((z - z_focal) / z_R)^2)
                z_r = 35.0  # Rayleigh range in mm
                beam_width_ratio = math.sqrt(1.0 + ((depth_mm - focal_depth) / z_r) ** 2)

                # Two-way attenuation along ray
                # Add current voxel attenuation
                cum_attenuation_db += medium.attenuation_db_cm_mhz * (freq_mhz ** medium.attenuation_exponent) * step_ds_cm

                # Check for severe shadowing (Calculus or Bone or Bowel gas)
                if medium.tissue_class in (AcousticTissueClass.CALCULUS_OXALATE, AcousticTissueClass.CALCULUS_URIC, AcousticTissueClass.CORTICAL_BONE):
                    stone_shadow_found = True
                    # Significant extra attenuation step to create dense posterior shadow cone
                    cum_attenuation_db += 8.0 * step_ds_cm * 10.0

                if medium.tissue_class == AcousticTissueClass.URINE_FLUID:
                    fluid_enhancement_found = True

                # Roundtrip intensity
                atten_factor = compute_two_way_attenuation_intensity(
                    cum_attenuation_db,
                    frequency_mhz=1.0,  # frequency was already folded into cum_attenuation_db
                )

                # TGC curve: counteracts nominal attenuation (exp(+2 * k * alpha_nom * f * d))
                tgc_gain = math.exp(2.0 * LN10_DIV_10 * nominal_alpha_db * freq_mhz * (depth_mm * 0.1))
                tgc_gain = min(tgc_gain, 120.0)  # Max amplifier clamp

                # Base backscatter intensity
                scatter = medium.backscatter_coefficient

                # Echo envelope before speckle
                raw_echo = scatter * atten_factor * tgc_gain / beam_width_ratio
                envelope_matrix[row_idx, col_idx] = max(0.0, raw_echo)

        # 6. Apply Rayleigh Distributed Speckle Texture
        # Rayleigh distribution parameter scale sigma = sqrt(2/pi) * mean
        rayleigh_noise = self.rng.rayleigh(scale=1.0, size=envelope_matrix.shape)
        # Modulate speckle: high scatterer density preserves texture, low scatterer (fluid) stays dark
        speckle_blended = envelope_matrix * (0.6 + 0.4 * rayleigh_noise)

        # 7. Render Needle if trajectory provided
        needle_rendered = False
        if needle_trajectory is not None:
            entry_pt, target_pt, insertion_depth = needle_trajectory
            traj_vec = target_pt - entry_pt
            traj_len = np.linalg.norm(traj_vec)
            if traj_len > 1e-4:
                traj_dir = traj_vec / traj_len
                current_tip = entry_pt + min(insertion_depth, traj_len) * traj_dir

                # Needle visibility calculation
                navi_eval = calculate_needle_acoustic_visibility(
                    needle_tangent=traj_dir,
                    beam_propagation_direction=probe_pose.axial_direction,
                    elevational_offset_mm=0.0,
                    elevational_slice_fwhm_mm=self.probe.elevation_slice_thickness_mm,
                )

                needle_brightness = max(0.2, navi_eval.navi_score) * 2.5

                # Project needle points onto the sector image grid
                for s in np.linspace(0.0, min(insertion_depth, traj_len), 80):
                    n_pt = entry_pt + s * traj_dir
                    # Distance from probe surface
                    diff_from_orig = n_pt - probe_pose.origin
                    depth_along_axial = float(np.dot(diff_from_orig, probe_pose.axial_direction))
                    lat_along_probe = float(np.dot(diff_from_orig, probe_pose.lateral_direction))

                    if 0.0 <= depth_along_axial <= max_depth:
                        r_idx = int(round((depth_along_axial / max_depth) * (n_depths - 1)))
                        # Scanline index for curvilinear or linear
                        if self.probe.transducer_type == TransducerType.CURVILINEAR:
                            r_c = self.probe.radius_of_curvature_mm
                            angle_rad = math.atan2(lat_along_probe, depth_along_axial + r_c)
                            half_angle = self.probe.sector_angle_rad / 2.0
                            c_ratio = (angle_rad + half_angle) / (2.0 * half_angle)
                        else:
                            half_w = self.probe.footprint_width_mm / 2.0
                            c_ratio = (lat_along_probe + half_w) / (2.0 * half_w)

                        c_idx = int(round(c_ratio * (n_lines - 1)))
                        if 0 <= r_idx < n_depths and 0 <= c_idx < n_lines:
                            speckle_blended[r_idx, c_idx] = max(
                                speckle_blended[r_idx, c_idx],
                                needle_brightness,
                            )
                            needle_rendered = True

        # 8. Logarithmic Dynamic Range Compression (60-80 dB -> 8-bit [0, 255])
        max_val = float(np.max(speckle_blended))
        if max_val <= 1e-6:
            compressed = np.zeros_like(speckle_blended, dtype=np.uint8)
        else:
            norm_env = speckle_blended / max_val
            # S_disp = 255 * ln(1 + gamma * S) / ln(1 + gamma)
            log_compressed = 255.0 * (np.log(1.0 + self.compression_gamma * norm_env) / np.log(1.0 + self.compression_gamma))
            compressed = np.clip(log_compressed, 0, 255).astype(np.uint8)

        angles_deg = np.linspace(-self.probe.sector_angle_deg / 2.0, self.probe.sector_angle_deg / 2.0, n_lines)

        return BModeSimulationResult(
            image_uint8=compressed,
            depth_axis_mm=depth_steps,
            lateral_angles_deg=angles_deg,
            probe_id=self.probe.probe_id,
            stone_shadow_detected=stone_shadow_found,
            fluid_enhancement_detected=fluid_enhancement_found,
            needle_rendered=needle_rendered,
            mean_echogenicity=float(np.mean(compressed)),
        )

    def simulate_synthetic_phantom(
        self,
        has_stone: bool = True,
        has_needle: bool = True,
        stone_depth_mm: float = 65.0,
        needle_angle_deg: float = 45.0,
    ) -> BModeSimulationResult:
        """
        Generates canonical synthetic renal ultrasound B-mode phantom slice
        containing skin, subcutaneous fat, kidney parenchyma, calyx lumen,
        dense stone with shadow cone, and needle.
        """
        n_lines = self.probe.num_scanlines
        n_depths = self.probe.num_depth_samples
        max_depth = self.probe.max_imaging_depth_mm

        depth_steps = np.linspace(0.0, max_depth, n_depths)
        angles_deg = np.linspace(-self.probe.sector_angle_deg / 2.0, self.probe.sector_angle_deg / 2.0, n_lines)

        img = np.zeros((n_depths, n_lines), dtype=np.float32)

        stone_shadow_found = False
        fluid_enhancement_found = False
        needle_rendered = False

        # Stone position in image grid
        stone_r = int(round((stone_depth_mm / max_depth) * n_depths))
        stone_c = n_lines // 2
        stone_radius_px = 6

        for r in range(n_depths):
            d_mm = depth_steps[r]
            for c in range(n_lines):
                # Layering:
                # 0 - 15 mm: Subcutaneous fat (moderate speckle)
                # 15 - 30 mm: Abdominal muscle (medium echogenicity)
                # 30 - 120 mm: Renal parenchyma (fine speckle)
                if d_mm < 15.0:
                    base_val = 0.35
                elif d_mm < 30.0:
                    base_val = 0.50
                elif d_mm < 120.0:
                    # Kidney parenchyma
                    base_val = 0.42
                    # Calyx lumen near center (anechoic fluid)
                    calyx_dist = math.hypot(r - (stone_r - 8), c - stone_c)
                    if calyx_dist < 10.0:
                        base_val = 0.05
                        fluid_enhancement_found = True
                else:
                    base_val = 0.25

                # Distal fluid enhancement (posterior to calyx lumen)
                if fluid_enhancement_found and (stone_r - 8) < r < stone_r and abs(c - stone_c) < 8:
                    base_val *= 1.3

                # Stone
                if has_stone:
                    dist_to_stone = math.hypot(r - stone_r, c - stone_c)
                    if dist_to_stone <= stone_radius_px:
                        # Bright hyperechoic anterior stone border
                        base_val = 1.0
                    elif r > stone_r and abs(c - stone_c) <= stone_radius_px:
                        # Posterior Acoustic Shadow Cone
                        base_val *= 0.05
                        stone_shadow_found = True

                img[r, c] = base_val

        # Add speckle
        rayleigh_noise = self.rng.rayleigh(scale=1.0, size=img.shape)
        speckle_blended = img * (0.65 + 0.35 * rayleigh_noise)

        # Render needle
        if has_needle:
            needle_rendered = True
            # Angle in deg relative to beam
            phi_rad = math.radians(needle_angle_deg)
            sin2_phi = math.sin(phi_rad) ** 2
            navi_score = sin2_phi ** 2.0  # p = 2.0
            needle_amp = max(0.2, navi_score) * 2.2

            # Needle entering from upper lateral corner toward stone
            start_r, start_c = 10, int(n_lines * 0.15)
            end_r, end_c = stone_r - 2, stone_c
            for t in np.linspace(0.0, 1.0, 100):
                nr = int(round(start_r + t * (end_r - start_r)))
                nc = int(round(start_c + t * (end_c - start_c)))
                if 0 <= nr < n_depths and 0 <= nc < n_lines:
                    speckle_blended[nr, nc] = max(speckle_blended[nr, nc], needle_amp)

        # Log compression
        max_val = float(np.max(speckle_blended))
        if max_val <= 1e-6:
            compressed = np.zeros_like(speckle_blended, dtype=np.uint8)
        else:
            norm_env = speckle_blended / max_val
            log_compressed = 255.0 * (np.log(1.0 + self.compression_gamma * norm_env) / np.log(1.0 + self.compression_gamma))
            compressed = np.clip(log_compressed, 0, 255).astype(np.uint8)

        return BModeSimulationResult(
            image_uint8=compressed,
            depth_axis_mm=depth_steps,
            lateral_angles_deg=angles_deg,
            probe_id=self.probe.probe_id,
            stone_shadow_detected=stone_shadow_found,
            fluid_enhancement_detected=fluid_enhancement_found,
            needle_rendered=needle_rendered,
            mean_echogenicity=float(np.mean(compressed)),
        )


def generate_simulated_bmode_ultrasound(
    ct_volume: Optional[np.ndarray] = None,
    voxel_spacing_mm: Tuple[float, float, float] = (1.0, 1.0, 1.0),
    volume_origin_mm: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    probe: Optional[TransducerProfile] = None,
    probe_pose: Optional[UltrasoundProbePose] = None,
    needle_trajectory: Optional[Tuple[np.ndarray, np.ndarray, float]] = None,
    has_stone: bool = True,
    has_needle: bool = True,
) -> BModeSimulationResult:
    """Convenience helper to run simulated B-mode ultrasound on CT or synthetic phantom."""
    sim = BModeUltrasoundSimulator(probe=probe or CURVILINEAR_C5_2)
    if ct_volume is not None and probe_pose is not None:
        return sim.simulate_from_ct_volume(
            ct_volume=ct_volume,
            voxel_spacing_mm=voxel_spacing_mm,
            volume_origin_mm=volume_origin_mm,
            probe_pose=probe_pose,
            needle_trajectory=needle_trajectory,
        )
    return sim.simulate_synthetic_phantom(
        has_stone=has_stone,
        has_needle=has_needle,
    )
