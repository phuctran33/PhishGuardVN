# PhishGuardVN — Flutter Web design system

Product: Cybersecurity Platform / Phishing URL Detection. Scope: one URL checker, Flutter/Dart + Material 3. No dashboard, invented telemetry, accounts or extra services.

## Method and precedence

UI UX Pro Max CLI **2.15.0**, official repository https://github.com/nextlevelbuilder/ui-ux-pro-max-skill, installed globally for Codex in `~/.agents/skills/ui-ux-pro-max`. Read SKILL.md and ran its Python search/design-system workflow on 09/11/2026. The CLI recommends restarting the assistant for automatic discovery; this session manually loaded the skill and executed its scripts successfully.

Searches:

```sh
python3 ~/.agents/skills/ui-ux-pro-max/scripts/search.py "cybersecurity phishing glassmorphism dark" --design-system -p PhishGuardVN -f markdown
python3 ~/.agents/skills/ui-ux-pro-max/scripts/search.py "glassmorphism minimal SaaS" --design-system --persist -p PhishGuardVN --output-dir apps/web -f markdown
python3 ~/.agents/skills/ui-ux-pro-max/scripts/search.py "glassmorphism" --domain style -n 1
python3 ~/.agents/skills/ui-ux-pro-max/scripts/search.py "responsive theme accessibility" --stack flutter -n 3
```

The first result recommended Cyberpunk; it was rejected as inconsistent with the brief. The narrower search verified Glassmorphism. This master curates the generated seed: the user's dark navy/cyan/red requirements override the generic SaaS blue/orange/light palette and its “avoid dark by default” suggestion. Flutter Material icons and locally bundled Roboto replace React icon libraries and remote Google Fonts. No React/CSS/GSAP runtime is added. Existing API contract, inference and acceptance criteria remain authoritative.

## Visual direction

Primary: restrained Glassmorphism. Theme: dark only, as requested. Layout: Minimalism / Swiss — strong left alignment, asymmetric two-column desktop grid, deliberate whitespace, a single primary action and clear type hierarchy. Mobile stacks content vertically. Desktop content maximum 1180 logical pixels; gutters 20/40; column gap 56; two columns only when available content width is at least 860.

One clipped frosted input/result card: 12px backdrop blur, 88% navy surface opacity, 1px outline, radius 24. Background has one quiet navy radial tonal change; no animated glow, parallax, decorative charts or fake counters. Results and errors use opaque tinted surfaces for legibility. No ornamental animation; mobile scroll-to-feedback is 250ms, zero with reduced motion; loading switches to a static hourglass plus explicit busy text with reduced motion.

## Semantic tokens (lib/main.dart)

| Token | Hex | Role |
|---|---|---|
| navy | #081321 | Background, input, text on CTA |
| surface | #132536 | Glass card, composed at 88% over navy background |
| ink | #EDF5FC | Primary text |
| muted | #ADC0D0 | Secondary text |
| teal | #65DECF | CTA, focus, benign indicator |
| line | #385266 | Decorative separators/card outline |
| controlBorder | #668598 | Input boundary |
| danger | #FF9BA3 | Readable red phishing/error text and icon |
| dangerSurface | #34232F | Phishing/error surface |
| benignSurface | #133534 | Benign surface |
| warning | #EBC283 | API degraded/offline indicator, also stated in text |

Do not communicate status by color alone: phishing has warning icon, explicit heading, model label and next action. Benign wording never promises safety. Probability is uncalibrated predict_proba; decision margin never has a percentage.

## Typography, spacing and controls

Local Roboto regular/bold, including Vietnamese glyphs and bundled Apache license. Material 3 text and form primitives; headings 32/44, card title 22, primary body/input/button 16, secondary copy 12/13. Body line height 1.5–1.7. Spacing follows 4/8dp tiers with a few optical icon/text adjustments. No fixed-height text containers, forced ellipsis or suppressed text scaling. Long model names and labels wrap.

Input has a persistent label, URL keyboard, visible cyan 2px focus outline, inline validation, preserved value after error. CTA minimum 48×56; retry minimum 48×48. Material states preserve keyboard activation and disabled semantics. Loading prevents duplicate submissions. Offline/timeout/API errors retain retry; no synthetic fallback. Header status wraps instead of colliding at narrow widths or increased font size.

## Verification expectations

Test 320px and 375px phones, tablet/landscape, desktop; verify large text/reduced motion, no overflow, keyboard Tab/Enter, loading, benign, phishing, invalid URL, timeout/offline and retry. Normal ink/muted text ≥4.5:1 on all state surfaces; navy CTA text ≥4.5:1 on teal; input boundary ≥3:1; measured using Flutter luminance tests. Real browser tests use the actual local FastAPI and existing fitted E1 pipeline; synthetic fixtures only in unit/widget tests. Teacher E2 v1 acceptance remains pending #16. See reports/week6_web_verification.md for actual results and limits.
