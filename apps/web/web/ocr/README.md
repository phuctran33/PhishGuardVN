# Browser OCR assets

PhishGuardVN loads these files from the Web origin when the image comparison
runs. The browser worker receives the normalized image in memory. Web keeps
the reading in the current dialog and sends a URL to FastAPI after the user
selects it and runs a check.

| Upstream | Revision | Files |
|---|---|---|
| [Tesseract.js](https://github.com/naptha/tesseract.js/tree/v7.0.0) | npm tesseract.js 7.0.0 | tesseract.min.js, worker.min.js and the supplied license texts |
| [Tesseract.js Core](https://github.com/naptha/tesseract.js-core/tree/v7.0.0) | npm tesseract.js-core 7.0.0 | tesseract-core-lstm.js, tesseract-core-lstm.wasm and license |
| [tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast/tree/87416418657359cb625c412a48b6e1d6d41c29bd) | 87416418657359cb625c412a48b6e1d6d41c29bd | English and Vietnamese models compressed with gzip, plus license |

The scalar LSTM build provides one compatible core and keeps the bundle to
about 5.3 MiB. SHA256SUMS pins the exact files. Verify from this directory with
shasum -a 256 -c SHA256SUMS. The runtime, worker, core and models are static
assets included in the Flutter Web release build.

See the [upstream local installation guide](https://github.com/naptha/tesseract.js/blob/v7.0.0/docs/local-installation.md).
