(() => {
  const WIDTH = 1080;
  const HEIGHT = 1350;
  const PAGE_SIZE = 3;
  const ENDPOINT = '/api/v1/current-reading/image-payment/';
  const BACKGROUNDS = Array.from(
    { length: 11 },
    (_, index) => `https://s3.ru1.storage.beget.cloud/0a648590a767-openhearted-anastasiya/static/monat/monat_${index + 1}.png`,
  );
  const proxyImageUrl = (url) => `/api/v1/vk-app/image-proxy/?url=${encodeURIComponent(url)}`;

  let fontPromise;
  const ensureFont = () => {
    if (fontPromise) return fontPromise;
    fontPromise = (async () => {
      if (typeof FontFace === 'undefined' || !document.fonts) return;
      const face = new FontFace('Great Vibes', 'url(/static/fonts/GreatVibes-Regular.ttf)');
      document.fonts.add(await face.load());
    })().catch(() => undefined);
    return fontPromise;
  };

  const operationId = (prefix) => window.crypto?.randomUUID
    ? `${prefix}-${window.crypto.randomUUID()}`
    : `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;

  const getCsrfToken = () => {
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  };

  const fetchJson = async (url, options = {}) => {
    const response = await fetch(url, {
      credentials: 'same-origin',
      ...options,
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken(),
        ...(options.headers || {}),
      },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
    return payload;
  };

  const loadImage = (url, proxy = true) => new Promise((resolve) => {
    if (!url) return resolve(null);
    const image = new Image();
    image.crossOrigin = 'anonymous';
    image.onload = () => resolve(image);
    image.onerror = () => resolve(null);
    image.src = proxy ? proxyImageUrl(url) : url;
  });

  const roundedPath = (ctx, x, y, width, height, radius) => {
    const r = Math.min(radius, width / 2, height / 2);
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + width, y, x + width, y + height, r);
    ctx.arcTo(x + width, y + height, x, y + height, r);
    ctx.arcTo(x, y + height, x, y, r);
    ctx.arcTo(x, y, x + width, y, r);
    ctx.closePath();
  };

  const drawCroppedImage = (ctx, image, x, y, width, height, radius = 18) => {
    roundedPath(ctx, x, y, width, height, radius);
    ctx.save();
    ctx.clip();
    if (!image) {
      const gradient = ctx.createLinearGradient(x, y, x + width, y + height);
      gradient.addColorStop(0, '#2f7758');
      gradient.addColorStop(1, '#ba6252');
      ctx.fillStyle = gradient;
      ctx.fillRect(x, y, width, height);
    } else {
      const sourceWidth = image.naturalWidth || image.width;
      const sourceHeight = image.naturalHeight || image.height;
      const scale = Math.max(width / sourceWidth, height / sourceHeight);
      const drawWidth = sourceWidth * scale;
      const drawHeight = sourceHeight * scale;
      ctx.drawImage(image, x + (width - drawWidth) / 2, y + (height - drawHeight) / 2, drawWidth, drawHeight);
    }
    ctx.restore();
  };

  const fitLines = (ctx, text, maxWidth, maxLines) => {
    const words = String(text || '').trim().split(/\s+/).filter(Boolean);
    const lines = [];
    let line = '';
    words.forEach((word) => {
      const candidate = line ? `${line} ${word}` : word;
      if (ctx.measureText(candidate).width <= maxWidth) line = candidate;
      else if (lines.length < maxLines) {
        if (line) lines.push(line);
        line = word;
      }
    });
    if (line && lines.length < maxLines) lines.push(line);
    if (lines.length === maxLines && words.join(' ').length > lines.join(' ').length) {
      let last = lines[maxLines - 1];
      while (last && ctx.measureText(`${last}…`).width > maxWidth) last = last.slice(0, -1).trim();
      lines[maxLines - 1] = `${last}…`;
    }
    return lines;
  };

  const drawFormatIcon = (ctx, code, x, y) => {
    ctx.save();
    ctx.strokeStyle = '#28634a';
    ctx.lineWidth = 3;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    if (code === 'audiobook') {
      ctx.beginPath();
      ctx.arc(x + 12, y + 12, 10, Math.PI, 0);
      ctx.stroke();
      ctx.strokeRect(x, y + 11, 5, 11);
      ctx.strokeRect(x + 19, y + 11, 5, 11);
    } else if (code === 'ebook') {
      roundedPath(ctx, x + 3, y, 18, 24, 3);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(x + 9, y + 19);
      ctx.lineTo(x + 15, y + 19);
      ctx.stroke();
    } else {
      ctx.beginPath();
      ctx.moveTo(x + 12, y + 4);
      ctx.quadraticCurveTo(x + 5, y, x + 1, y + 4);
      ctx.lineTo(x + 1, y + 21);
      ctx.quadraticCurveTo(x + 6, y + 17, x + 12, y + 22);
      ctx.quadraticCurveTo(x + 18, y + 17, x + 23, y + 21);
      ctx.lineTo(x + 23, y + 4);
      ctx.quadraticCurveTo(x + 19, y, x + 12, y + 4);
      ctx.stroke();
    }
    ctx.restore();
  };

  const formatDetail = (format) => {
    if (format.code === 'audiobook') return [format.position, format.total].filter(Boolean).join(' из ') || format.label;
    if (format.current_page != null && format.total_pages) return `${Math.round(format.current_page)} из ${format.total_pages} стр.`;
    return format.label;
  };

  const bookCardLayouts = (count) => {
    if (count === 1) {
      return [{
        x: 90, y: 471, width: 900, height: 560,
        coverX: 122, coverY: 516, coverWidth: 284, coverHeight: 438,
        textX: 450, textWidth: 492,
        titleY: 542, titleSize: 42,
        authorY: 660, authorSize: 30,
        percentY: 754, percentSize: 54,
        barY: 716, pagesY: 805, pagesSize: 28,
        formatsY: 856, formatSize: 21,
      }];
    }
    if (count === 2) {
      return [0, 1].map((index) => {
        const y = 329 + index * 424;
        return {
          x: 70, y, width: 940, height: 400,
          coverX: 98, coverY: y + 34, coverWidth: 216, coverHeight: 332,
          textX: 350, textWidth: 612,
          titleY: y + 48, titleSize: 36,
          authorY: y + 140, authorSize: 27,
          percentY: y + 213, percentSize: 44,
          barY: y + 181, pagesY: y + 258, pagesSize: 25,
          formatsY: y + 305, formatSize: 19,
        };
      });
    }
    return [0, 1, 2].map((index) => {
      const y = 285 + index * 320;
      return {
        x: 54, y, width: 972, height: 300,
        coverX: 76, coverY: y + 18, coverWidth: 172, coverHeight: 264,
        textX: 274, textWidth: 704,
        titleY: y + 52, titleSize: 34,
        authorY: y + 132, authorSize: 26,
        percentY: y + 185, percentSize: 38,
        barY: y + 158, pagesY: y + 221, pagesSize: 24,
        formatsY: y + 240, formatSize: 20,
      };
    });
  };

  const drawBookCard = (ctx, book, cover, layout) => {
    const { x, y, width, height } = layout;
    roundedPath(ctx, x, y, width, height, 30);
    ctx.fillStyle = 'rgba(255, 255, 255, .76)';
    ctx.fill();
    ctx.strokeStyle = 'rgba(38, 93, 69, .35)';
    ctx.lineWidth = 2;
    ctx.stroke();

    drawCroppedImage(
      ctx,
      cover,
      layout.coverX,
      layout.coverY,
      layout.coverWidth,
      layout.coverHeight,
    );
    const { textX, textWidth } = layout;
    ctx.fillStyle = '#173d2e';
    ctx.font = `800 ${layout.titleSize}px Arial, sans-serif`;
    fitLines(ctx, book.title, textWidth, 2).forEach((line, index) => {
      ctx.fillText(line, textX, layout.titleY + index * (layout.titleSize + 5));
    });
    ctx.fillStyle = '#5b6c64';
    ctx.font = `${layout.authorSize}px Arial, sans-serif`;
    const author = (book.authors || []).join(', ') || 'Автор не указан';
    ctx.fillText(fitLines(ctx, author, textWidth, 1)[0] || author, textX, layout.authorY);

    const percent = Math.max(0, Math.min(100, Number(book.percent || 0)));
    ctx.fillStyle = '#b85c4a';
    ctx.font = `800 ${layout.percentSize}px Arial, sans-serif`;
    ctx.fillText(`${Math.round(percent)}%`, textX, layout.percentY);
    const percentWidth = layout.percentSize * 2.5;
    roundedPath(ctx, textX + percentWidth, layout.barY, textWidth - percentWidth, 18, 9);
    ctx.fillStyle = 'rgba(30, 75, 56, .16)';
    ctx.fill();
    if (percent > 0) {
      roundedPath(ctx, textX + percentWidth, layout.barY, (textWidth - percentWidth) * percent / 100, 18, 9);
      ctx.fillStyle = '#2f7758';
      ctx.fill();
    }
    ctx.fillStyle = '#314d41';
    ctx.font = `${layout.pagesSize}px Arial, sans-serif`;
    const pages = book.current_page != null && book.total_pages
      ? `${Math.round(book.current_page)} из ${book.total_pages} стр.`
      : 'Прогресс по трекеру';
    ctx.fillText(pages, textX, layout.pagesY);

    let formatX = textX;
    for (const format of (book.formats || []).slice(0, 3)) {
      const detail = formatDetail(format);
      ctx.font = `${layout.formatSize}px Arial, sans-serif`;
      const pillWidth = Math.min(textWidth, Math.max(118, ctx.measureText(detail).width + 55));
      roundedPath(ctx, formatX, layout.formatsY, pillWidth, 40, 20);
      ctx.fillStyle = 'rgba(225, 238, 231, .94)';
      ctx.fill();
      drawFormatIcon(ctx, format.code, formatX + 10, layout.formatsY + 8);
      ctx.fillStyle = '#274d3c';
      ctx.fillText(detail, formatX + 42, layout.formatsY + 27);
      formatX += pillWidth + 9;
      if (formatX > x + width - 120) break;
    }
  };

  const renderPages = async (books, backgroundIndexes) => {
    await ensureFont();
    const chunks = Array.from(
      { length: Math.ceil(books.length / PAGE_SIZE) },
      (_, index) => books.slice(index * PAGE_SIZE, (index + 1) * PAGE_SIZE),
    );
    const logo = await loadImage('/static/img/logo_1.png', false);
    const canvases = [];
    for (let pageIndex = 0; pageIndex < chunks.length; pageIndex += 1) {
      const background = await loadImage(BACKGROUNDS[backgroundIndexes[pageIndex] || 0]);
      const covers = await Promise.all(chunks[pageIndex].map((book) => loadImage(book.cover_url)));
      const canvas = document.createElement('canvas');
      canvas.width = WIDTH;
      canvas.height = HEIGHT;
      const ctx = canvas.getContext('2d');
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = 'high';
      if (background) drawCroppedImage(ctx, background, 0, 0, WIDTH, HEIGHT, 0);
      else { ctx.fillStyle = '#e9f1ec'; ctx.fillRect(0, 0, WIDTH, HEIGHT); }
      ctx.fillStyle = 'rgba(16, 46, 34, .13)';
      ctx.fillRect(0, 0, WIDTH, HEIGHT);

      roundedPath(ctx, 54, 36, WIDTH - 108, 190, 30);
      ctx.fillStyle = 'rgba(255, 255, 255, .74)';
      ctx.fill();
      ctx.fillStyle = '#173d2e';
      ctx.font = '72px "Great Vibes", cursive';
      ctx.textAlign = 'center';
      ctx.fillText('Я читаю сейчас', WIDTH / 2, 105);
      ctx.font = '800 26px Arial, sans-serif';
      const brand = 'Калейдоскоп книг';
      const brandWidth = ctx.measureText(brand).width;
      const logoSize = 50;
      const brandStart = (WIDTH - logoSize - 14 - brandWidth) / 2;
      ctx.textAlign = 'left';
      if (logo) drawCroppedImage(ctx, logo, brandStart, 124, logoSize, logoSize, 10);
      ctx.fillText(brand, brandStart + logoSize + 14, 158);
      ctx.textAlign = 'center';
      ctx.font = '700 20px Arial, sans-serif';
      ctx.fillText(`${pageIndex + 1} / ${chunks.length}`, WIDTH / 2, 208);
      ctx.textAlign = 'left';

      const layouts = bookCardLayouts(chunks[pageIndex].length);
      chunks[pageIndex].forEach((book, index) => drawBookCard(ctx, book, covers[index], layouts[index]));

      roundedPath(ctx, 54, HEIGHT - 74, WIDTH - 108, 42, 21);
      ctx.fillStyle = 'rgba(31, 88, 63, .88)';
      ctx.fill();
      ctx.fillStyle = '#fff';
      ctx.font = '700 21px Arial, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('kalejdoskopknig.ru', WIDTH / 2, HEIGHT - 46);
      canvases.push(canvas);
    }
    return canvases;
  };

  const downloadCanvas = (canvas, filename) => {
    const link = document.createElement('a');
    link.download = filename;
    link.href = canvas.toDataURL('image/jpeg', .95);
    document.body.appendChild(link);
    link.click();
    link.remove();
  };

  const ensureModal = () => {
    let modal = document.querySelector('[data-current-reading-image-modal]');
    if (modal) return modal;
    modal = document.createElement('div');
    modal.className = 'current-reading-image-modal';
    modal.hidden = true;
    modal.dataset.currentReadingImageModal = '';
    modal.innerHTML = `
      <div class="current-reading-image-modal__backdrop" data-current-reading-image-close></div>
      <section class="current-reading-image-modal__dialog" role="dialog" aria-modal="true" aria-label="Я читаю сейчас">
        <header class="current-reading-image-modal__header">
          <div><small>Для истории</small><strong>Я читаю сейчас</strong></div>
          <button type="button" class="current-reading-image-modal__close" data-current-reading-image-close aria-label="Закрыть">×</button>
        </header>
        <div class="current-reading-image-modal__body">
          <div class="current-reading-image-modal__quote" data-current-reading-image-quote>Загружаем данные…</div>
          <div class="current-reading-image-modal__preview" data-current-reading-image-preview>Подготавливаем данные…</div>
          <div class="current-reading-image-modal__pager" data-current-reading-image-pager hidden>
            <button type="button" class="btn btn-outline-dark btn-sm" data-current-reading-image-prev>Назад</button>
            <strong data-current-reading-image-page></strong>
            <button type="button" class="btn btn-outline-dark btn-sm" data-current-reading-image-next>Вперёд</button>
          </div>
          <p class="current-reading-image-modal__message" data-current-reading-image-message></p>
        </div>
        <footer class="current-reading-image-modal__footer">
          <button type="button" class="btn btn-outline-dark" data-current-reading-image-background hidden>Сменить фон · 5 ◉</button>
          <button type="button" class="btn btn-outline-dark" data-current-reading-image-download-all hidden>Скачать все</button>
          <button type="button" class="btn btn-dark" data-current-reading-image-download hidden>Скачать JPG</button>
          <button type="button" class="btn btn-dark" data-current-reading-image-generate>Создать · 20 ◉</button>
        </footer>
      </section>`;
    document.body.appendChild(modal);
    return modal;
  };

  document.addEventListener('click', async (event) => {
    const trigger = event.target.closest('.js-current-reading-image');
    if (!trigger) return;
    event.preventDefault();
    event.stopPropagation();

    const modal = ensureModal();
    const quoteNode = modal.querySelector('[data-current-reading-image-quote]');
    const preview = modal.querySelector('[data-current-reading-image-preview]');
    const message = modal.querySelector('[data-current-reading-image-message]');
    const generateButton = modal.querySelector('[data-current-reading-image-generate]');
    const backgroundButton = modal.querySelector('[data-current-reading-image-background]');
    const downloadButton = modal.querySelector('[data-current-reading-image-download]');
    const downloadAllButton = modal.querySelector('[data-current-reading-image-download-all]');
    const pager = modal.querySelector('[data-current-reading-image-pager]');
    const pageLabel = modal.querySelector('[data-current-reading-image-page]');
    const previousButton = modal.querySelector('[data-current-reading-image-prev]');
    const nextButton = modal.querySelector('[data-current-reading-image-next]');
    let quote;
    let canvases = [];
    let currentPage = 0;
    let backgroundIndexes = [];

    const setMessage = (text, isError = false) => {
      message.textContent = text || '';
      message.classList.toggle('is-error', isError);
    };
    const updatePreview = () => {
      preview.replaceChildren(canvases[currentPage]);
      pageLabel.textContent = `${currentPage + 1} / ${canvases.length}`;
      previousButton.disabled = currentPage === 0;
      nextButton.disabled = currentPage >= canvases.length - 1;
      pager.hidden = canvases.length < 2;
    };
    const rerender = async () => {
      canvases = await renderPages(quote.books, backgroundIndexes);
      currentPage = Math.min(currentPage, canvases.length - 1);
      updatePreview();
    };

    modal.hidden = false;
    document.body.style.overflow = 'hidden';
    quoteNode.textContent = 'Загружаем данные…';
    preview.textContent = 'Подготавливаем данные…';
    setMessage('');
    generateButton.hidden = false;
    backgroundButton.hidden = true;
    downloadButton.hidden = true;
    downloadAllButton.hidden = true;
    pager.hidden = true;

    try {
      quote = await fetchJson(ENDPOINT);
      const payment = quote.generation;
      quoteNode.innerHTML = `<span><strong>До 3 книг на изображении</strong><br><small>Баланс: ${payment.unlimited ? 'без ограничений' : `${payment.balance ?? 0} монет`}</small></span><span class="current-reading-image-modal__price">${payment.unlimited ? 'Бесплатно' : `${payment.cost} ◉`}</span>`;
      generateButton.textContent = payment.unlimited ? 'Создать' : `Создать · ${payment.cost} ◉`;
      backgroundButton.textContent = quote.background.unlimited ? 'Сменить фон' : `Сменить фон · ${quote.background.cost} ◉`;
      generateButton.disabled = !quote.books.length;
      preview.textContent = quote.books.length
        ? `Будет создано изображений: ${quote.page_count}. Подтвердите создание.`
        : 'На полке «Читаю» пока нет книг с активным трекером.';
    } catch (error) {
      quoteNode.textContent = 'Не удалось получить данные полки.';
      preview.textContent = 'Предпросмотр недоступен.';
      setMessage(error.message, true);
      generateButton.hidden = true;
      return;
    }

    generateButton.onclick = async () => {
      generateButton.disabled = true;
      setMessage('Создаём изображения…');
      try {
        const result = await fetchJson(ENDPOINT, {
          method: 'POST',
          body: JSON.stringify({ action: 'generate', operation_id: operationId('current-reading') }),
        });
        backgroundIndexes = Array(quote.page_count).fill(0).map(() => Math.floor(Math.random() * BACKGROUNDS.length));
        await rerender();
        generateButton.hidden = true;
        backgroundButton.hidden = false;
        downloadButton.hidden = false;
        downloadAllButton.hidden = canvases.length < 2;
        setMessage(`Готово. Изображений: ${canvases.length}. Баланс: ${result.unlimited ? 'без ограничений' : result.balance_after}.`);
      } catch (error) {
        setMessage(error.message, true);
      } finally {
        generateButton.disabled = false;
      }
    };

    backgroundButton.onclick = async () => {
      backgroundButton.disabled = true;
      setMessage('Меняем фон выбранного изображения…');
      try {
        const result = await fetchJson(ENDPOINT, {
          method: 'POST',
          body: JSON.stringify({
            action: 'change_background',
            operation_id: operationId(`current-reading-bg-${currentPage}`),
            page_index: currentPage,
          }),
        });
        backgroundIndexes[currentPage] = ((backgroundIndexes[currentPage] || 0) + 1) % BACKGROUNDS.length;
        await rerender();
        setMessage(`Фон изменён. Баланс: ${result.unlimited ? 'без ограничений' : result.balance_after}.`);
      } catch (error) {
        setMessage(error.message, true);
      } finally {
        backgroundButton.disabled = false;
      }
    };

    previousButton.onclick = () => { if (currentPage > 0) { currentPage -= 1; updatePreview(); } };
    nextButton.onclick = () => { if (currentPage < canvases.length - 1) { currentPage += 1; updatePreview(); } };
    downloadButton.onclick = () => downloadCanvas(canvases[currentPage], `kalejdoskop-reading-now-${currentPage + 1}.jpg`);
    downloadAllButton.onclick = () => canvases.forEach((canvas, index) => {
      window.setTimeout(() => downloadCanvas(canvas, `kalejdoskop-reading-now-${index + 1}.jpg`), index * 250);
    });

    modal.querySelectorAll('[data-current-reading-image-close]').forEach((button) => {
      button.onclick = () => {
        modal.hidden = true;
        document.body.style.overflow = '';
      };
    });
  });
})();
