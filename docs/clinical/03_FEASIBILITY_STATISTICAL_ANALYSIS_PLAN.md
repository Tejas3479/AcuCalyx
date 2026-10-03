# AcuCalyx™ Feasibility Statistical Analysis Plan (SAP) & Estimands

**Document ID:** SAP-ACU-001  
**Version:** 1.0 (Frozen)  
**Governing Standard:** ISO 14155:2026 / ICH E9 (R1) Addendum on Estimands  
**Trial Identifier:** `ACU-PILOT-2026-01` ($N = 30$)  
**Target Milestone:** Milestone M6A Feasibility Analysis & Gate M6.5 Sizing Protocol  

---

## 1. Introduction & Statistical Scope

This Statistical Analysis Plan (SAP) specifies the formal biostatistical methodology, estimands, hypothesis tests, missing data strategies, and sample size recalculation algorithms for the **AcuCalyx™ Feasibility Pilot (ACU-PILOT-2026-01)**.

In strict compliance with **ISO 14155:2026** and **ICH E9(R1)**:
1. Endpoints are formalized using the **Estimand Framework** (Population, Variable, Intercurrent Events, Summary Measure).
2. The primary statistical goal of Milestone M6A is to generate **authoritative empirical variance, effect size, and clustering estimates** to govern the design of any subsequent pivotal study (Gate M6.5).

---

## 2. Formal Estimand Specifications (ICH E9 / ISO 14155:2026)

### 2.1 Estimand 1: Fluoroscopy Access Time
- **Population:** Adult patients (age $\ge 18$) presenting with unilateral renal calculus disease undergoing planned elective PCNL using standardized biplanar fluoroscopic access guidance.
- **Variable:** Total Fluoroscopy Access Time ($t_{access}$, seconds), defined from the first puncture-related fluoroscopic exposure until objective confirmation of calyx entry and aspiration.
- **Intercurrent Events:**
  - *Conversion to Ultrasound Rescue (after failed fluoroscopy):* Handled via **Treatment-Policy Strategy** (the total fluoroscopy time accumulated prior to rescue is counted).
  - *Procedure Abandonment / Cancellation:* Handled via **Composite Strategy** (imputed at the 99th percentile of observed times or evaluated in sensitivity set).
- **Summary Measure:** Difference in mean log-transformed access time, accompanied by Hodges-Lehmann median difference estimator and 95% confidence intervals.

### 2.2 Estimand 2: Initial Puncture Success ($\le 2$ Passes)
- **Population:** Same as Estimand 1.
- **Variable:** Binary indicator of successful access to the pre-documented intended target calyx within $\le 2$ distinct needle puncture passes without tract abandonment ($1 = \text{Success}, 0 = \text{Failure}$).
- **Intercurrent Events:** Ultrasound rescue or tract abandonment counted as $0$ (Failure).
- **Summary Measure:** Risk Difference and Odds Ratio with exact Clopper-Pearson 95% binomial confidence intervals.

---

## 3. Analysis Populations

- **Intention-to-Treat (ITT) Population:** All randomized subjects in whom renal access is attempted, analyzed according to their randomized arm regardless of protocol deviations or device technical failures.
- **Per-Protocol (PP) Population:** All randomized subjects who complete procedural access without major protocol violations (e.g. baseline CT slice thickness $>2.5\text{ mm}$, uncalibrated C-arm use).
- **Safety Population:** All subjects enrolled who undergo patient positioning in the operating room.

---

## 4. Statistical Methods for Milestone M6A

### 4.1 Descriptive Analysis
Continuous variables (fluoroscopy time, procedure duration, KAP/DAP, air kerma, depth, angular deviation) will be summarized with: Mean, Standard Deviation, Median, Interquartile Range (IQR), Minimum, and Maximum. Categorical variables (pass count category, plan adoption category, Clavien-Dindo grade) will be summarized with counts and percentages.

### 4.2 Inferential Comparisons (Exploratory in M6A)
1. **Access Time Distribution:**
   Given the typical positive skewness of procedural time data:
   $$\log(t_{access}) \sim \text{Normal}(\mu, \sigma^2)$$
   Evaluated using independent two-sample t-test on log-scale and non-parametric Mann-Whitney U test with Hodges-Lehmann median estimator.
2. **Puncture Pass Success Rate:**
   Evaluated using Fisher's exact test and Cochran-Mantel-Haenszel (CMH) test stratified by Guy's Stone Score (I/II vs. III/IV).
3. **Surgeon Clustering Evaluation:**
   To assess surgeon-level clustering effects for pivotal trial sizing, the Intraclass Correlation Coefficient (ICC) will be estimated via one-way random effects ANOVA:
   $$\text{ICC} = \frac{\sigma^2_{\text{surgeon}}}{\sigma^2_{\text{surgeon}} + \sigma^2_{\text{residual}}}$$

---

## 5. Gate M6.5: Pivotal Trial Sizing Protocol (Conditional M6B)

Upon database lock and analysis of Milestone M6A:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   DECISION GATE M6.5 SIZING ALGORITHM                  │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│   Step 1: Extract Observed Standard Deviation s_pilot from M6A.        │
│   Step 2: Extract Observed Surgeon Clustering ICC from M6A.            │
│   Step 3: Define Clinically Meaningful Delta (with FDA CDRH consensus)│
│   Step 4: Compute Design Effect:                                       │
│           DEFF = 1 + (m_bar - 1) * ICC                                 │
│           (where m_bar is average patients per surgeon)                │
│   Step 5: Compute Pivotal Sample Size per Arm:                         │
│           N_pivotal = [ 2 * (z_alpha/2 + z_beta)^2 * s^2 / Delta^2 ]   │
│                       * DEFF * [ 1 / (1 - Attrition) ]                 │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

This mathematical protocol guarantees that if a pivotal trial is required, its sample size will be derived from **real human clinical distributions** rather than speculative literature guesses.
