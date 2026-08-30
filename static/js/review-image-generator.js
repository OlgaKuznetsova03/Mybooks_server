(() => {
  const WIDTH = 1080;
  const HEIGHT = 1350;
  const proxyImageUrl = (url) => `/api/v1/vk-app/image-proxy/?url=${encodeURIComponent(url)}`;

  let handwrittenFontPromise = null;
  const ensureHandwrittenFont = () => {
    if (handwrittenFontPromise) return handwrittenFontPromise;
    handwrittenFontPromise = (async () => {
      if (typeof FontFace === 'undefined' || !document.fonts) return;
      const face = new FontFace('Great Vibes', 'url(/static/fonts/GreatVibes-Regular.ttf)');
      const loaded = await face.load();
      document.fonts.add(loaded);
    })().catch(() => undefined);
    return handwrittenFontPromise;
  };

  const operationId = (prefix) => {
    if (window.crypto?.randomUUID) return `${prefix}-${window.crypto.randomUUID()}`;
    return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  };

  const getCsrfToken = () => {
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  };

  const loadImage = (url) => new Promise((resolve, reject) => {
    if (!url) {
      resolve(null);
      return;
    }
    const image = new Image();
    image.crossOrigin = 'anonymous';
    image.onload = () => resolve(image);
    image.onerror = reject;
    image.src = proxyImageUrl(url);
  });

  const loadDirectImage = (url) => new Promise((resolve, reject) => {
    if (!url) {
      resolve(null);
      return;
    }
    const image = new Image();
    image.crossOrigin = 'anonymous';
    image.onload = () => resolve(image);
    image.onerror = reject;
    image.src = url;
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

  const drawGlassCard = (ctx, x, y, width, height, alpha = 0.58) => {
    roundedPath(ctx, x, y, width, height, 26);
    ctx.fillStyle = `rgba(255, 255, 255, ${alpha})`;
    ctx.fill();
    ctx.strokeStyle = 'rgba(41, 91, 69, .36)';
    ctx.lineWidth = 2;
    ctx.stroke();
  };

  const drawCover = (ctx, image, x, y, width, height) => {
    roundedPath(ctx, x, y, width, height, 18);
    ctx.save();
    ctx.clip();
    if (!image) {
      ctx.fillStyle = '#e9eee9';
      ctx.fillRect(x, y, width, height);
      ctx.fillStyle = '#315442';
      ctx.font = '700 28px Arial, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('Нет обложки', x + width / 2, y + height / 2);
    } else {
      const scale = Math.max(width / image.width, height / image.height);
      const drawWidth = image.width * scale;
      const drawHeight = image.height * scale;
      ctx.drawImage(
        image,
        x + (width - drawWidth) / 2,
        y + (height - drawHeight) / 2,
        drawWidth,
        drawHeight,
      );
    }
    ctx.restore();
  };

  const wrapLines = (ctx, text, maxWidth) => {
    const paragraphs = String(text || '').replace(/\r/g, '').split('\n');
    const lines = [];
    paragraphs.forEach((paragraph) => {
      const words = paragraph.trim().split(/\s+/).filter(Boolean);
      if (!words.length) return;
      let line = words.shift();
      words.forEach((word) => {
        const candidate = `${line} ${word}`;
        if (ctx.measureText(candidate).width <= maxWidth) line = candidate;
        else {
          lines.push(line);
          line = word;
        }
      });
      lines.push(line);
    });
    return lines;
  };

  const splitReview = (review) => {
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    ctx.font = '34px Arial, sans-serif';
    const lines = wrapLines(ctx, review, 880);
    const pages = [];
    const firstPageLines = 9;
    const continuationLines = 17;
    pages.push(lines.splice(0, firstPageLines));
    while (lines.length) pages.push(lines.splice(0, continuationLines));
    return pages.length ? pages : [[]];
  };

  const drawFitText = (ctx, text, x, y, maxWidth, startSize, minSize, weight = 700) => {
    let size = startSize;
    do {
      ctx.font = `${weight} ${size}px Arial, sans-serif`;
      if (ctx.measureText(text).width <= maxWidth) break;
      size -= 2;
    } while (size > minSize);
    ctx.fillText(text, x, y);
  };

  const drawBackground = (ctx, image) => {
    ctx.fillStyle = '#e8ece8';
    ctx.fillRect(0, 0, WIDTH, HEIGHT);
    if (!image) return;
    const scale = Math.max(WIDTH / image.width, HEIGHT / image.height);
    const drawWidth = image.width * scale;
    const drawHeight = image.height * scale;
    ctx.drawImage(image, (WIDTH - drawWidth) / 2, (HEIGHT - drawHeight) / 2, drawWidth, drawHeight);
  };

  const drawPage = ({ background, cover, logo, data, lines, index, total }) => {
    const canvas = document.createElement('canvas');
    canvas.width = WIDTH;
    canvas.height = HEIGHT;
    const ctx = canvas.getContext('2d');
    drawBackground(ctx, background);

    ctx.fillStyle = 'rgba(255,255,255,.70)';
    roundedPath(ctx, 55, 45, 970, 1260, 34);
    ctx.fill();
    ctx.strokeStyle = 'rgba(41,91,69,.25)';
    ctx.lineWidth = 2;
    ctx.stroke();

    if (logo) drawCover(ctx, logo, 82, 70, 74, 74);
    ctx.fillStyle = '#1e4937';
    ctx.textAlign = 'left';
    drawFitText(ctx, 'Калейдоскоп книг', logo ? 174 : 82, 120, 520, 36, 28, 800);
    ctx.textAlign = 'right';
    ctx.fillStyle = '#c49a2d';
    ctx.font = '800 38px Arial, sans-serif';
    ctx.fillText(`★ ${data.score || '—'}/10`, 990, 120);
    ctx.textAlign = 'left';

    if (index === 0) {
      drawGlassCard(ctx, 72, 165, 936, 410, 0.60);
      drawCover(ctx, cover, 92, 190, 228, 350);
      ctx.fillStyle = '#193d2f';
      drawFitText(ctx, data.book_title || 'Книга', 352, 230, 620, 43, 28, 800);
      ctx.fillStyle = '#58675f';
      drawFitText(ctx, data.book_author || '', 352, 280, 620, 30, 22, 500);

      const dateLabel = data.reading_start_label && data.reading_end_label
        ? `${data.reading_start_label} — ${data.reading_end_label}`
        : data.reading_end_label || data.created_label || 'Дата не указана';
      const meta = [
        `Прочитано: ${dateLabel}`,
        data.format_labels?.length ? data.format_labels.join(', ') : null,
        data.reading_days ? `${data.reading_days} дн.` : null,
        data.total_pages ? `${data.total_pages} стр.` : null,
      ].filter(Boolean);
      ctx.font = '28px Arial, sans-serif';
      ctx.fillStyle = '#43574d';
      meta.forEach((item, metaIndex) => ctx.fillText(item, 352, 345 + metaIndex * 42));

      const scores = Array.isArray(data.category_scores) ? data.category_scores : [];
      if (scores.length) {
        ctx.fillStyle = 'rgba(233, 244, 238, .72)';
        roundedPath(ctx, 342, 470, 646, 82, 20);
        ctx.fill();
        ctx.font = '700 23px Arial, sans-serif';
        ctx.fillStyle = '#315442';
        const scoreText = scores.map((score) => `${score.label}: ${score.value}`).join('  ·  ');
        const scoreLines = wrapLines(ctx, scoreText, 606).slice(0, 2);
        scoreLines.forEach((line, scoreIndex) => ctx.fillText(line, 364, 502 + scoreIndex * 29));
      }

      drawGlassCard(ctx, 72, 594, 936, 552, 0.56);
      ctx.fillStyle = '#1e4937';
      ctx.font = '58px "Great Vibes", cursive';
      ctx.fillText('Отзыв на книгу', 96, 661);
      ctx.fillStyle = '#24352d';
      ctx.font = '34px Arial, sans-serif';
      lines.forEach((line, lineIndex) => ctx.fillText(line, 96, 716 + lineIndex * 47));
    } else {
      drawGlassCard(ctx, 72, 165, 936, 150, 0.60);
      drawCover(ctx, cover, 88, 180, 90, 120);
      ctx.fillStyle = '#1e4937';
      ctx.font = '800 34px Arial, sans-serif';
      ctx.fillText(data.book_title || 'Продолжение отзыва', 202, 218);
      ctx.font = '700 27px Arial, sans-serif';
      ctx.fillStyle = '#66766e';
      ctx.fillText(`Продолжение отзыва · страница ${index + 1}`, 202, 264);

      drawGlassCard(ctx, 72, 335, 936, 811, 0.56);
      ctx.fillStyle = '#1e4937';
      ctx.font = '52px "Great Vibes", cursive';
      ctx.fillText('Отзыв на книгу', 96, 397);
      ctx.fillStyle = '#24352d';
      ctx.font = '34px Arial, sans-serif';
      lines.forEach((line, lineIndex) => ctx.fillText(line, 96, 448 + lineIndex * 42));
    }

    ctx.fillStyle = 'rgba(31,73,55,.92)';
    roundedPath(ctx, 72, 1215, 936, 64, 18);
    ctx.fill();
    ctx.fillStyle = '#fff';
    ctx.font = '700 24px Arial, sans-serif';
    ctx.fillText(`@${data.username || 'читатель'}`, 95, 1256);
    ctx.textAlign = 'center';
    ctx.fillText(`${index + 1} / ${total}`, 540, 1256);
    ctx.textAlign = 'right';
    ctx.fillText(data.site_label || 'kalejdoskopknig.ru', 985, 1256);
    return canvas;
  };

  const ensureModal = () => {
    let modal = document.getElementById('reviewImageModal');
    if (modal) return modal;
    modal = document.createElement('div');
    modal.id = 'reviewImageModal';
    modal.className = 'review-image-modal';
    modal.hidden = true;
    modal.innerHTML = `
      <div class="review-image-modal__backdrop" data-review-image-close></div>
      <section class="review-image-modal__dialog" role="dialog" aria-modal="true" aria-labelledby="reviewImageTitle">
        <header class="review-image-modal__header">
          <div><small class="text-muted">Изображение с отзывом</small><h2 class="h5 mb-0" id="reviewImageTitle">Поделиться впечатлением</h2></div>
          <button class="review-image-modal__close" type="button" data-review-image-close aria-label="Закрыть">×</button>
        </header>
        <div class="review-image-modal__body">
          <div class="review-image-modal__quote" data-review-image-quote></div>
          <div class="review-image-modal__preview" data-review-image-preview><span>Подготавливаем данные…</span></div>
          <div class="review-image-modal__pager" data-review-image-pager hidden>
            <button class="btn btn-outline-secondary btn-sm" type="button" data-review-image-prev>Назад</button>
            <strong data-review-image-page>1 / 1</strong>
            <button class="btn btn-outline-secondary btn-sm" type="button" data-review-image-next>Вперёд</button>
          </div>
          <div class="review-image-modal__message" data-review-image-message></div>
        </div>
        <footer class="review-image-modal__footer">
          <button class="btn btn-primary" type="button" data-review-image-generate>Создать</button>
          <button class="btn btn-outline-primary" type="button" data-review-image-background hidden>Сменить фон · 5 ◉</button>
          <button class="btn btn-primary" type="button" data-review-image-download hidden>Скачать JPG</button>
          <button class="btn btn-outline-secondary" type="button" data-review-image-download-all hidden>Скачать все</button>
        </footer>
      </section>`;
    document.body.appendChild(modal);
    return modal;
  };

  const fetchJson = async (url, options = {}) => {
    const response = await fetch(url, {
      credentials: 'same-origin',
      ...options,
      headers: {
        Accept: 'application/json',
        ...(options.body ? { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() } : {}),
        ...(options.headers || {}),
      },
    });
    let payload = {};
    try { payload = await response.json(); } catch (_) { payload = {}; }
    if (!response.ok) throw Object.assign(new Error(payload.detail || `HTTP ${response.status}`), { payload });
    return payload;
  };

  const downloadCanvas = (canvas, filename) => {
    const link = document.createElement('a');
    link.download = filename;
    link.href = canvas.toDataURL('image/jpeg', .94);
    document.body.appendChild(link);
    link.click();
    link.remove();
  };

  document.addEventListener('click', async (event) => {
    const trigger = event.target.closest('.js-review-image');
    if (!trigger) return;
    event.preventDefault();
    event.stopPropagation();

    const modal = ensureModal();
    const endpoint = trigger.dataset.endpoint;
    const quoteNode = modal.querySelector('[data-review-image-quote]');
    const preview = modal.querySelector('[data-review-image-preview]');
    const message = modal.querySelector('[data-review-image-message]');
    const generateButton = modal.querySelector('[data-review-image-generate]');
    const backgroundButton = modal.querySelector('[data-review-image-background]');
    const downloadButton = modal.querySelector('[data-review-image-download]');
    const downloadAllButton = modal.querySelector('[data-review-image-download-all]');
    const pager = modal.querySelector('[data-review-image-pager]');
    const pageLabel = modal.querySelector('[data-review-image-page]');
    const previousButton = modal.querySelector('[data-review-image-prev]');
    const nextButton = modal.querySelector('[data-review-image-next]');

    let quote;
    let pages = [];
    let currentPage = 0;
    let backgroundIndexes = [];
    let imageCache = {};
    const generationOperationId = operationId('review');

    const setMessage = (text, error = false) => {
      message.textContent = text || '';
      message.classList.toggle('is-error', error);
    };
    const updatePreview = () => {
      preview.replaceChildren(pages[currentPage]);
      pageLabel.textContent = `${currentPage + 1} / ${pages.length}`;
      previousButton.disabled = currentPage === 0;
      nextButton.disabled = currentPage >= pages.length - 1;
    };
    const render = async () => {
      await ensureHandwrittenFont();
      const reviewPages = splitReview(quote.review.review);
      const [logo, cover] = await Promise.all([
        loadDirectImage(quote.review.logo_url).catch(() => null),
        loadImage(quote.review.book_cover_url).catch(() => null),
      ]);
      pages = [];
      for (let index = 0; index < reviewPages.length; index += 1) {
        const backgroundIndex = backgroundIndexes[index] ?? 0;
        const backgroundUrl = quote.backgrounds[backgroundIndex];
        if (!(backgroundUrl in imageCache)) {
          imageCache[backgroundUrl] = await loadImage(backgroundUrl).catch(() => null);
        }
        pages.push(drawPage({
          background: imageCache[backgroundUrl],
          cover,
          logo,
          data: quote.review,
          lines: reviewPages[index],
          index,
          total: reviewPages.length,
        }));
      }
      currentPage = Math.min(currentPage, pages.length - 1);
      updatePreview();
      pager.hidden = pages.length < 2;
      backgroundButton.hidden = false;
      downloadButton.hidden = false;
      downloadAllButton.hidden = pages.length < 2;
    };

    modal.hidden = false;
    document.body.style.overflow = 'hidden';
    preview.innerHTML = '<span>Подготавливаем данные…</span>';
    setMessage('');
    generateButton.hidden = false;
    backgroundButton.hidden = true;
    downloadButton.hidden = true;
    downloadAllButton.hidden = true;
    pager.hidden = true;

    try {
      quote = await fetchJson(endpoint);
      const payment = quote.generation;
      quoteNode.innerHTML = `
        <span><strong>Генерация комплекта</strong><br><small>Баланс: ${payment.unlimited ? 'без ограничений' : `${payment.balance} монет`}</small></span>
        <span class="review-image-modal__price">${payment.unlimited ? 'Бесплатно' : `${payment.cost} ◉`}</span>`;
      generateButton.textContent = payment.unlimited ? 'Создать' : `Создать · ${payment.cost} ◉`;
      preview.innerHTML = '<span>После подтверждения здесь появится предпросмотр.</span>';
      backgroundButton.textContent = quote.background.unlimited ? 'Сменить фон' : `Сменить фон · ${quote.background.cost} ◉`;
    } catch (error) {
      quoteNode.textContent = 'Не удалось получить данные отзыва.';
      preview.innerHTML = '<span>Предпросмотр недоступен.</span>';
      setMessage(error.message, true);
      generateButton.hidden = true;
      return;
    }

    generateButton.onclick = async () => {
      generateButton.disabled = true;
      setMessage('Создаём изображения…');
      try {
        const result = await fetchJson(endpoint, {
          method: 'POST',
          body: JSON.stringify({ action: 'generate', operation_id: generationOperationId }),
        });
        quote = result;
        const pageCount = splitReview(quote.review.review).length;
        backgroundIndexes = Array(pageCount).fill(result.background_index || 0);
        await render();
        generateButton.hidden = true;
        setMessage(`Готово. Создано изображений: ${pages.length}. Баланс: ${result.unlimited ? 'без ограничений' : result.balance_after}.`);
      } catch (error) {
        setMessage(error.message, true);
      } finally {
        generateButton.disabled = false;
      }
    };

    backgroundButton.onclick = async () => {
      backgroundButton.disabled = true;
      setMessage('Меняем фон выбранной страницы…');
      try {
        const result = await fetchJson(endpoint, {
          method: 'POST',
          body: JSON.stringify({
            action: 'change_background',
            operation_id: operationId(`review-bg-${currentPage}`),
            page_index: currentPage,
            current_background_index: backgroundIndexes[currentPage] || 0,
          }),
        });
        quote = result;
        backgroundIndexes[currentPage] = result.background_index || 0;
        await render();
        setMessage(`Фон изменён. Баланс: ${result.unlimited ? 'без ограничений' : result.balance_after}.`);
      } catch (error) {
        setMessage(error.message, true);
      } finally {
        backgroundButton.disabled = false;
      }
    };

    previousButton.onclick = () => { if (currentPage > 0) { currentPage -= 1; updatePreview(); } };
    nextButton.onclick = () => { if (currentPage < pages.length - 1) { currentPage += 1; updatePreview(); } };
    downloadButton.onclick = () => downloadCanvas(pages[currentPage], `kalejdoskop-review-${quote.review.id}-${currentPage + 1}.jpg`);
    downloadAllButton.onclick = () => pages.forEach((canvas, index) => {
      window.setTimeout(() => downloadCanvas(canvas, `kalejdoskop-review-${quote.review.id}-${index + 1}.jpg`), index * 220);
    });

    modal.querySelectorAll('[data-review-image-close]').forEach((button) => {
      button.onclick = () => {
        modal.hidden = true;
        document.body.style.overflow = '';
      };
    });
  });
})();
