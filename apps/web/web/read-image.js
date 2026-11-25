/* Local OCR bridge. The runtime, language data and worker all use this Web origin. */
(() => {
  const root = new URL('ocr/', document.currentScript.src);
  const asset = name => new URL(name, root).href;
  let runtime;

  function loadRuntime() {
    runtime ??= new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = asset('tesseract.min.js');
      script.onload = resolve;
      script.onerror = () => {
        script.remove();
        runtime = undefined;
        reject(new Error('Could not load local OCR'));
      };
      document.head.append(script);
    });
    return runtime;
  }

  globalThis.phishGuardReadImage = bytes => {
    let worker;
    let cancelled = false;
    let rejectJob;
    const interruption = new Promise((_, reject) => { rejectJob = reject; });
    const cancel = () => {
      cancelled = true;
      rejectJob(new Error('OCR cancelled or timed out'));
    };
    const timer = setTimeout(cancel, 45000);
    const release = () => {
      if (worker) {
        const finished = worker;
        worker = undefined;
        void finished.terminate();
      }
    };
    const recognize = async () => {
      await loadRuntime();
      if (cancelled) return;
      worker = await globalThis.Tesseract.createWorker('eng+vie', 1, {
        workerPath: asset('worker.min.js'),
        corePath: asset('tesseract-core-lstm.js'),
        langPath: root.href,
        workerBlobURL: false,
        cacheMethod: 'none',
        errorHandler: rejectJob,
      });
      if (cancelled) {
        release();
        return;
      }
      // PSM 11 finds sparse labels around a QR and in screenshots.
      await worker.setParameters({ tessedit_pageseg_mode: '11' });
      const { data } = await worker.recognize(bytes, {}, { text: true, blocks: true });
      const lines = (data.blocks || []).flatMap(block =>
        block.paragraphs.flatMap(paragraph =>
          paragraph.lines.map(line => ({ text: line.text, box: line.bbox }))
        )
      );
      return JSON.stringify(lines);
    };
    return {
      cancel,
      result: Promise.race([recognize(), interruption]).finally(() => {
        clearTimeout(timer);
        release();
      }),
    };
  };
})();
