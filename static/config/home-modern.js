(() => {
  const getCookie = (name) => {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    return parts.length === 2 ? parts.pop().split(';').shift() : '';
  };

  const iconMapNode = document.getElementById('home-reaction-icon-map');
  const iconMap = iconMapNode ? JSON.parse(iconMapNode.textContent || '{}') : {};

  const getIconUrl = (emoji) => {
    if (!emoji) return '';
    if (iconMap[emoji]) return iconMap[emoji];
    const normalized = emoji.replace(/\uFE0F/g, '');
    if (iconMap[normalized]) return iconMap[normalized];
    const match = Object.entries(iconMap).find(([key]) => key.replace(/\uFE0F/g, '') === normalized);
    return match ? match[1] : '';
  };

  const appendReactionIcon = (button, emoji) => {
    const iconUrl = getIconUrl(emoji);
    if (iconUrl) {
      const image = document.createElement('img');
      image.src = iconUrl;
      image.alt = emoji;
      image.loading = 'lazy';
      image.addEventListener('error', () => {
        const fallback = document.createElement('span');
        fallback.setAttribute('aria-hidden', 'true');
        fallback.textContent = emoji;
        image.replaceWith(fallback);
      }, { once: true });
      button.appendChild(image);
      return;
    }

    const fallback = document.createElement('span');
    fallback.setAttribute('aria-hidden', 'true');
    fallback.textContent = emoji;
    button.appendChild(fallback);
  };

  const createReactionButton = (emoji, count, active) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `tracker-reaction${active ? ' is-active' : ''}`;
    button.dataset.emoji = emoji;
    appendReactionIcon(button, emoji);

    if (count !== null && count !== undefined) {
      const counter = document.createElement('span');
      counter.dataset.count = '';
      counter.textContent = String(count);
      button.appendChild(counter);
      button.setAttribute('aria-label', `Реакция ${emoji}: ${count}`);
    } else {
      button.setAttribute('aria-label', `Поставить реакцию ${emoji}`);
    }
    return button;
  };

  const renderReactionSummary = (widget, reactions, activeEmojis) => {
    const list = widget.querySelector('[data-reaction-list]');
    if (!list) return;

    const activeSet = new Set(Array.isArray(activeEmojis) ? activeEmojis : []);
    list.replaceChildren();

    if (!Array.isArray(reactions) || reactions.length === 0) {
      const empty = document.createElement('span');
      empty.className = 'tracker-reactions__empty';
      empty.textContent = 'Пока без реакций';
      list.appendChild(empty);
      return;
    }

    reactions.forEach((reaction) => {
      list.appendChild(createReactionButton(
        reaction.emoji,
        reaction.count,
        activeSet.has(reaction.emoji),
      ));
    });
  };

  const closeReactionPickers = (exceptWidget = null) => {
    document.querySelectorAll('[data-reaction-picker]:not([hidden])').forEach((picker) => {
      const widget = picker.closest('[data-reaction-widget]');
      if (widget && widget === exceptWidget) return;
      picker.hidden = true;
      const toggle = widget?.querySelector('[data-reaction-toggle]');
      if (toggle) toggle.setAttribute('aria-expanded', 'false');
    });
  };

  const toggleReactionPicker = (button) => {
    const widget = button.closest('[data-reaction-widget]');
    const picker = widget?.querySelector('[data-reaction-picker]');
    if (!widget || !picker) return;

    const shouldOpen = picker.hidden;
    closeReactionPickers(widget);
    picker.hidden = !shouldOpen;
    button.setAttribute('aria-expanded', String(shouldOpen));
  };

  const updateReaction = async (button) => {
    const widget = button.closest('[data-reaction-widget]');
    const reactUrl = widget?.dataset.reactUrl;
    const emoji = button.dataset.emoji;
    if (!widget || !reactUrl || !emoji || widget.dataset.pending === 'true') return;

    widget.dataset.pending = 'true';
    const body = new URLSearchParams({ emoji });

    try {
      const response = await fetch(reactUrl, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'X-CSRFToken': getCookie('csrftoken'),
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: body.toString(),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.ok) throw new Error(payload.error || `HTTP ${response.status}`);

      const ownEmojis = Array.isArray(payload.user_emojis) ? payload.user_emojis : [];
      renderReactionSummary(widget, payload.reactions || [], ownEmojis);
      widget.querySelectorAll('[data-reaction-picker] .tracker-reaction').forEach((pickerButton) => {
        pickerButton.classList.toggle('is-active', ownEmojis.includes(pickerButton.dataset.emoji));
      });
    } catch (error) {
      console.error('Не удалось обновить реакцию', error);
    } finally {
      delete widget.dataset.pending;
    }
  };

  const activateCommunityTab = (root, tabName) => {
    root.querySelectorAll('[data-community-tab]').forEach((button) => {
      const active = button.dataset.communityTab === tabName;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-selected', String(active));
      button.tabIndex = active ? 0 : -1;
    });

    root.querySelectorAll('[data-community-panel]').forEach((panel) => {
      panel.hidden = panel.dataset.communityPanel !== tabName;
    });
  };

  document.addEventListener('click', (event) => {
    const target = event.target instanceof Element ? event.target : null;
    if (!target) return;

    const communityTab = target.closest('[data-community-tab]');
    if (communityTab) {
      const root = communityTab.closest('[data-community-tabs]');
      if (root) activateCommunityTab(root, communityTab.dataset.communityTab);
      return;
    }

    const reactionToggle = target.closest('[data-reaction-toggle]');
    if (reactionToggle) {
      event.preventDefault();
      toggleReactionPicker(reactionToggle);
      return;
    }

    const reactionButton = target.closest('.tracker-reaction');
    if (reactionButton?.closest('[data-reaction-widget]')) {
      event.preventDefault();
      updateReaction(reactionButton);
      return;
    }

    if (!target.closest('[data-reaction-widget]')) closeReactionPickers();
  });

  document.querySelectorAll('[data-community-tabs]').forEach((root) => {
    activateCommunityTab(root, 'clubs');
  });
})();
