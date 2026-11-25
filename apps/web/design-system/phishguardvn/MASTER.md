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

Restrained glassmorphism with deep navy and cyan. The Swiss layout uses left alignment and one primary action. The desktop grid starts at a viewport width of 960 logical pixels, with a 1220 maximum container, 40 gutters and a 54 column gap. Narrower layouts stack the headline, scanner and evidence, with 16 or 28 gutters.

The scanner has a navy surface gradient, quiet border, radius 22 and a soft shadow. An ImageGen illustration of a smoked-glass shield with a teal link inlay provides the desktop focal point. The local WebP is decorative and excluded from semantics. Results use separate tinted surfaces. Scroll-to-feedback takes 220 ms or runs instantly with reduced motion. Reduced motion also replaces the spinner with a static hourglass.

<details>
<summary>Studio illustration prompt</summary>

The built-in ImageGen produced the transparent source for [scan-shield.webp](../../assets/images/scan-shield.webp).

> Generate a single isolated premium 3D product illustration for PhishGuardVN's website URL scanner, transparent background, wide 3:2 composition. A thick, precise, translucent dark navy optical-glass shield, with a clean recessed interlocking chain-link symbol formed from two brushed pale teal inlays at the center, seems to hover a little above two thin offset smoked-glass square plates. Render from a restrained slightly elevated three-quarter angle, large and centered, straight architectural geometry, genuine bevels and transparent refraction, strong studio key on the upper-left edge and a soft cool fill. Deep blue-black and muted icy teal with tasteful mint highlights only; a sparse delicate dashed arced optical path close to the object is acceptable. Elegant Swiss grid industrial product photography and editorial cybersecurity, soft low-key contrast with a legible silhouette on a #081321 navy website. Leave modest clear space around every edge and enough room to see the base. No typography, letters, numbers, text, watermarks, padlocks, external logos, people, code rain, sci-fi cockpit, neon beams or busy particles. Real transparent alpha around the entire object and shadow.

</details>

## Semantic tokens (lib/main.dart)

| Token | Hex | Role |
|---|---|---|
| navy | #081321 | Background, input, text on CTA |
| surface | #132536 | Glass card and supporting tools |
| glassTop | #192E40 | Scanner surface highlight |
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

Local Roboto regular/bold covers Vietnamese glyphs. The page heading uses 36 on compact layouts and 58 on desktop. The scanner title is 23, the input and primary action are 16 and support copy is 12–14. Long names, labels and enlarged text wrap.

The URL label stays visible. Enter runs the scan. The paste action requires user interaction and keeps manual entry available when clipboard access is denied. Clearing the URL returns focus to the field. Focus outlines are 2 logical pixels, the main action is at least 48×54 and the text controls are at least 48×48. QR confirmation and supplemental tools remain accessible from the same page. Invalid URL errors offer **Chỉnh URL**. Connection and server failures offer retry.

## Verification expectations

Check desktop, tablet, 320px and 375px, 200% text scale, reduced motion, keyboard submission, loading, verdicts, validation and offline recovery. The Flutter contrast test requires normal text ≥4.5:1 and the input boundary ≥3:1. Browser smoke tests use FastAPI and the released stacking Teacher. The [Week 8–9 report](../../../../reports/week8_9_hung_verification.md) records which cases use fixtures or fault injection.
