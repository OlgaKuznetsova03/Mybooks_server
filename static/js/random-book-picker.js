(function () {
  'use strict';

  const API_URL = '/api/v1/random-book/';

  const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    "'": '&#39;',
    '"': '&quot;',
  }[character]));

  const getCookie = (name) => {
    const item = document.cookie
      .split(';')
      .map((value) => value.trim())
      .find((value) => value.startsWith(`${name}=`));
    return item ? decodeURIComponent(item.slice(name.length + 1)) : '';
  };

  const operationId = () => {
    if (window.crypto?.randomUUID) {
      return window.crypto.randomUUID().replaceAll('-', '');
    }
    return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  };

  const request = async (url, options) => {
    const response = await fetch(url, {
      credentials: 'same-origin',
      ...options,
      headers: {
        Accept: 'application/json',
        ...(options?.body ? { 'Content-Type': 'application/json' } : {}),
        ...(options?.method === 'POST' ? { 'X-CSRFToken': getCookie('csrftoken') } : {}),
        ...(options?.headers || {}),
      },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(payload.detail || `HTTP ${response.status}`);
      error.payload = payload;
      throw error;
    }
    return payload;
  };

  const createModal = () => {
    const overlay = document.createElement('div');
    overlay.className = 'random-book-modal';
    overlay.hidden = true;
    overlay.innerHTML = `
      <div class="random-book-modal__backdrop" data-random-close></div>
      <section class="random-book-modal__dialog" role="dialog" aria-modal="true" aria-labelledby="randomBookTitle">
        <header class="random-book-modal__header">
          <div>
            <span>Случайный выбор</span>
            <h2 id="randomBookTitle">Что читать дальше?</h2>
          </div>
          <button class="random-book-modal__close" type="button" data-random-close aria-label="Закрыть">&times;</button>
        </header>
        <div class="random-book-modal__body" data-random-body></div>
      </section>`;
    document.body.appendChild(overlay);
    return overlay;
  };

  const modal = createModal();
  const body = modal.querySelector('[data-random-body]');
  let activeTrigger = null;
  let quote = null;
  let activeOperationId = '';
  let selectedBook = null;

  const close = () => {
    modal.hidden = true;
    document.body.classList.remove('random-book-modal-open');
    activeTrigger?.focus();
  };

  modal.querySelectorAll('[data-random-close]').forEach((button) => {
    button.addEventListener('click', close);
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !modal.hidden) close();
  });

  const setStatus = (message, type = '') => {
    const status = body.querySelector('[data-random-status]');
    if (!status) return;
    status.textContent = message;
    status.className = `random-book-status ${type ? `random-book-status--${type}` : ''}`;
  };

  const renderQuote = () => {
    const balance = quote.unlimited ? 'без ограничений' : `${quote.coin_balance ?? 0} монет`;
    const payment = quote.unlimited ? 'Для Премиум списания не будет' : 'Стоимость выбора: 10 монет';
    body.innerHTML = `
      <div class="random-book-intro">
        <div class="random-book-intro__icon" aria-hidden="true">?</div>
        <div>
          <strong>${escapeHtml(quote.shelf_label)}</strong>
          <p>Выберем одну книгу среди непрочитанных и еще не начатых.</p>
        </div>
      </div>
      <div class="random-book-payment">
        <span>${payment}</span>
        <span>Ваш баланс: <strong>${balance}</strong></span>
      </div>
      <p class="random-book-count">Доступно книг: <strong>${quote.candidate_count}</strong></p>
      <p class="random-book-status" data-random-status></p>
      <div class="random-book-actions">
        <button class="btn btn-outline-secondary" type="button" data-random-close-action>Отмена</button>
        <button class="btn btn-primary" type="button" data-random-select ${quote.candidate_count ? '' : 'disabled'}>
          Выбрать за 10 монет
        </button>
      </div>`;
    body.querySelector('[data-random-close-action]').addEventListener('click', close);
    body.querySelector('[data-random-select]')?.addEventListener('click', selectBook);
  };

  const renderAnimation = (book) => {
    const covers = [...(quote.preview_books || []), book].filter((item) => item?.cover_url);
    const tiles = Array.from({ length: 12 }, (_, index) => {
      const item = covers[index % Math.max(covers.length, 1)] || null;
      return item
        ? `<img src="${escapeHtml(item.cover_url)}" alt="" style="--fall-index:${index};--fall-column:${index % 4}">`
        : `<span style="--fall-index:${index};--fall-column:${index % 4}">Книга</span>`;
    }).join('');
    body.innerHTML = `
      <div class="random-book-animation" aria-live="polite">
        <p>Выбираем книгу...</p>
        <div class="random-book-rain" aria-hidden="true">${tiles}</div>
      </div>`;
  };

  const renderResult = (book) => {
    const cover = book.cover_url
      ? `<img src="${escapeHtml(book.cover_url)}" alt="Обложка книги ${escapeHtml(book.title)}">`
      : '<div class="random-book-result__placeholder">Нет обложки</div>';
    body.innerHTML = `
      <div class="random-book-result">
        <span class="random-book-result__eyebrow">Ваш следующий выбор</span>
        ${cover}
        <h3>${escapeHtml(book.title)}</h3>
        <p>${escapeHtml(book.author)}</p>
      </div>
      <p class="random-book-status" data-random-status></p>
      <div class="random-book-actions random-book-actions--result">
        <button class="btn btn-primary" type="button" data-random-start>Начать читать</button>
        <a class="btn btn-outline-primary" href="${escapeHtml(book.detail_url)}">К книге</a>
      </div>`;
    body.querySelector('[data-random-start]').addEventListener('click', startReading);
  };

  async function selectBook() {
    const button = body.querySelector('[data-random-select]');
    if (button) button.disabled = true;
    setStatus('Проверяем баланс...', 'loading');
    activeOperationId = operationId();
    try {
      const response = await request(API_URL, {
        method: 'POST',
        body: JSON.stringify({
          action: 'select',
          shelf: activeTrigger.dataset.shelf,
          operation_id: activeOperationId,
        }),
      });
      selectedBook = response.book;
      renderAnimation(selectedBook);
      const duration = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 350 : 3000;
      window.setTimeout(() => renderResult(selectedBook), duration);
    } catch (error) {
      renderQuote();
      setStatus(error.message || 'Не удалось выбрать книгу.', 'error');
    }
  }

  async function startReading() {
    const button = body.querySelector('[data-random-start]');
    if (button) {
      button.disabled = true;
      button.textContent = 'Создаем трекер...';
    }
    try {
      const response = await request(API_URL, {
        method: 'POST',
        body: JSON.stringify({
          action: 'start_reading',
          shelf: activeTrigger.dataset.shelf,
          operation_id: activeOperationId,
          book_id: selectedBook.id,
        }),
      });
      window.location.href = response.tracker_url;
    } catch (error) {
      setStatus(error.message || 'Не удалось начать чтение.', 'error');
      if (button) {
        button.disabled = false;
        button.textContent = 'Начать читать';
      }
    }
  }

  const open = async (trigger) => {
    activeTrigger = trigger;
    quote = null;
    selectedBook = null;
    activeOperationId = '';
    modal.hidden = false;
    document.body.classList.add('random-book-modal-open');
    body.innerHTML = '<div class="random-book-loading"><span></span><p>Смотрим непрочитанные книги...</p></div>';
    try {
      quote = await request(`${API_URL}?shelf=${encodeURIComponent(trigger.dataset.shelf)}`);
      renderQuote();
    } catch (error) {
      body.innerHTML = '<p class="random-book-status random-book-status--error" data-random-status></p>';
      setStatus(error.message || 'Не удалось загрузить книги.', 'error');
    }
  };

  document.querySelectorAll('[data-random-book-picker]').forEach((trigger) => {
    trigger.addEventListener('click', () => void open(trigger));
  });
})();
