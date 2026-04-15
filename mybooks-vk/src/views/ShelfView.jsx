import React from 'react';

const getStyles = (isDarkTheme) => ({
  page: {
    minHeight: '100vh',
    background: isDarkTheme ? '#000000' : '#f3f4f8',
    color: isDarkTheme ? '#9ca3af' : '#1f2937',
    padding: '12px 12px 24px',
    boxSizing: 'border-box',
    fontFamily: 'Arial, sans-serif',
  },
  container: {
    maxWidth: '760px',
    margin: '0 auto',
  },
  headerCard: {
    background: isDarkTheme ? '#000000' : '#ffffff',
    borderRadius: '16px',
    padding: '14px',
    boxShadow: '0 4px 14px rgba(15, 23, 42, 0.06)',
    marginBottom: '16px',
  },
  topRow: {
    display: 'flex',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: '12px',
  },
  titleWrap: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '10px',
    flex: 1,
    minWidth: 0,
  },
  logo: {
    fontSize: '24px',
    lineHeight: 1,
    marginTop: '1px',
  },
  title: {
    margin: 0,
    fontSize: '22px',
    fontWeight: 800,
    color: isDarkTheme ? '#d1d5db' : '#111827',
    lineHeight: 1.15,
  },
  subtitle: {
    margin: '4px 0 0',
    fontSize: '13px',
    color: isDarkTheme ? '#9ca3af' : '#6b7280',
    lineHeight: 1.35,
  },
  logoutButton: {
    border: 'none',
    borderRadius: '10px',
    padding: '9px 14px',
    background: isDarkTheme ? '#8b5cf6' : '#111827',
    color: '#ffffff',
    fontSize: '13px',
    fontWeight: 700,
    cursor: 'pointer',
    flexShrink: 0,
  },
  profileCard: {
    marginTop: '12px',
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '10px 12px',
    background: isDarkTheme ? '#000000' : '#f8fafc',
    borderRadius: '12px',
  },
  avatar: {
    width: '42px',
    height: '42px',
    borderRadius: '50%',
    objectFit: 'cover',
    background: isDarkTheme ? '#1f1f1f' : '#e5e7eb',
    display: 'block',
    flexShrink: 0,
  },
  avatarFallback: {
    width: '42px',
    height: '42px',
    borderRadius: '50%',
    background: 'linear-gradient(135deg, #7c3aed, #2563eb)',
    color: '#fff',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontWeight: 800,
    fontSize: '13px',
    flexShrink: 0,
  },
  profileName: {
    margin: 0,
    fontSize: '15px',
    fontWeight: 700,
    background: isDarkTheme ? '#1f1f1f' : '#e5e7eb',
    lineHeight: 1.2,
  },
  profileMeta: {
    margin: '3px 0 0',
    fontSize: '12px',
    color: isDarkTheme ? '#9ca3af' : '#6b7280',
    lineHeight: 1.3,
  },
  section: {
    marginTop: '18px',
  },
  sectionTitle: {
    margin: '0 0 10px',
    fontSize: '18px',
    fontWeight: 800,
    color: isDarkTheme ? '#d1d5db' : '#111827',
  },
  booksGrid: {
    display: 'flex',
    overflowX: 'auto',
    overflowY: 'hidden',
    gap: '12px',
    paddingBottom: '8px',
    WebkitOverflowScrolling: 'touch',
    scrollbarWidth: 'thin',
  },
  bookCard: {
    background: isDarkTheme ? '#000000' : '#ffffff',
    borderRadius: '14px',
    padding: '8px',
    boxShadow: '0 4px 14px rgba(15, 23, 42, 0.06)',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    flex: '0 0 auto',
    width: '130px',
  },
  coverWrap: {
    position: 'relative',
    width: '100%',
  },
  badge: {
    position: 'absolute',
    top: '6px',
    left: '6px',
    zIndex: 2,
    padding: '4px 7px',
    borderRadius: '999px',
    fontSize: '10px',
    fontWeight: 700,
    color: '#fff',
    background: isDarkTheme ? '#8b5cf6' : '#111827',
    lineHeight: 1,
  },
  badgeReading: {
    background: '#4338ca',
  },
  badgeFinished: {
    background: '#059669',
  },
  progressBadge: {
    position: 'absolute',
    right: '6px',
    bottom: '6px',
    zIndex: 2,
    padding: '4px 7px',
    borderRadius: '999px',
    fontSize: '10px',
    fontWeight: 800,
    color: '#ffffff',
    background: isDarkTheme ? 'rgba(24, 24, 24, 0.9)' : 'rgba(17, 24, 39, 0.9)',
    lineHeight: 1,
    boxShadow: '0 2px 6px rgba(0,0,0,0.18)',
  },
  bookCover: {
    width: '100%',
    aspectRatio: '2 / 3',
    borderRadius: '10px',
    objectFit: 'cover',
    background: isDarkTheme ? '#1f1f1f' : '#e5e7eb',
    display: 'block',
  },
  bookCoverFallback: {
    width: '100%',
    aspectRatio: '2 / 3',
    borderRadius: '10px',
    background: isDarkTheme ? 'linear-gradient(135deg, #101010, #1f1f1f)' : 'linear-gradient(135deg, #f3f4f6, #e0e7ff)',
    color: isDarkTheme ? '#9ca3af' : '#374151',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    textAlign: 'center',
    padding: '8px',
    boxSizing: 'border-box',
    fontWeight: 700,
    fontSize: '11px',
    lineHeight: 1.2,
  },
  bookTitle: {
    margin: 0,
    fontSize: '13px',
    fontWeight: 700,
    color: isDarkTheme ? '#d1d5db' : '#111827',
    lineHeight: 1.25,
    display: '-webkit-box',
    WebkitLineClamp: 3,
    WebkitBoxOrient: 'vertical',
    overflow: 'hidden',
    minHeight: '48px',
  },
  bookAuthors: {
    margin: 0,
    fontSize: '11px',
    color: isDarkTheme ? '#9ca3af' : '#6b7280',
    lineHeight: 1.3,
    display: '-webkit-box',
    WebkitLineClamp: 2,
    WebkitBoxOrient: 'vertical',
    overflow: 'hidden',
    minHeight: '28px',
  },
  emptyCard: {
    background: isDarkTheme ? '#000000' : '#ffffff',
    borderRadius: '16px',
    padding: '14px',
    boxShadow: '0 4px 14px rgba(15, 23, 42, 0.06)',
    color: isDarkTheme ? '#9ca3af' : '#6b7280',
    fontSize: '14px',
  },
  statsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
    gap: '10px',
  },
  statCard: {
    background: isDarkTheme ? '#000000' : '#ffffff',
    borderRadius: '14px',
    padding: '12px',
    boxShadow: '0 4px 14px rgba(15, 23, 42, 0.06)',
    width: '85%',
    justifySelf: 'center',
  },
  statLabel: {
    margin: 0,
    fontSize: '10px',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    color: isDarkTheme ? '#9ca3af' : '#6b7280',
    fontWeight: 700,
    lineHeight: 1.3,
  },
  statValue: {
    margin: '8px 0 0',
    fontSize: '20px',
    fontWeight: 800,
    color: isDarkTheme ? '#d1d5db' : '#111827',
    lineHeight: 1.1,
  },
});

function getInitials(vkUser, data) {
  const source =
    `${vkUser?.first_name || ''} ${vkUser?.last_name || ''}`.trim() ||
    data?.profile?.username ||
    'U';

  return source
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('');
}

function renderCover(coverUrl, title, styles) {
  if (coverUrl) {
    return <img src={coverUrl} alt={title} style={styles.bookCover} />;
  }

  return <div style={styles.bookCoverFallback}>{title || 'Без обложки'}</div>;
}

function formatAudioValue(stats) {
  if (!stats) return '0 мин';

  if (stats.audio_tracked_display) {
    return stats.audio_tracked_display;
  }

  if (stats.audio_total_display) {
    return stats.audio_total_display;
  }

  if (typeof stats.audio_minutes_this_month === 'number') {
    const total = Math.round(stats.audio_minutes_this_month);

    if (total <= 0) return '0 мин';
    if (total < 60) return `${total} мин`;

    const hours = Math.floor(total / 60);
    const minutes = total % 60;

    if (!minutes) return `${hours} ч`;
    return `${hours} ч ${minutes} мин`;
  }

  return '0 мин';
}

function formatPagesValue(value) {
  const parsed = Number(value ?? 0);
  if (!Number.isFinite(parsed)) return 0;
  return Math.round(parsed);
}

function StatCard({ label, value, styles }) {
  return (
    <div style={styles.statCard}>
      <p style={styles.statLabel}>{label}</p>
      <p style={styles.statValue}>{value}</p>
    </div>
  );
}

export const ShelfView = ({ data, vkUser, onLogout, isDarkTheme = false }) => {
  const styles = getStyles(isDarkTheme);
  const profile = data?.profile || {};
  const currentBook = data?.current_book || null;
  const recentBooks = Array.isArray(data?.recent_books) ? data.recent_books : [];
  const stats = data?.stats || {};

  const displayName =
    `${vkUser?.first_name || ''} ${vkUser?.last_name || ''}`.trim() ||
    profile.username ||
    'Пользователь';

  const accountName = profile.username || profile.email || '—';

  const books = [];
  const usedIds = new Set();

  if (currentBook) {
    books.push({ ...currentBook, shelf_status: 'reading' });
    if (currentBook.id !== undefined && currentBook.id !== null) {
      usedIds.add(currentBook.id);
    }
  }

  recentBooks.forEach((book) => {
    if (!usedIds.has(book.id)) {
      books.push({ ...book, shelf_status: 'finished' });
      if (book.id !== undefined && book.id !== null) {
        usedIds.add(book.id);
      }
    }
  });

  const booksCount = Array.isArray(stats.books)
    ? stats.books.length
    : typeof stats.books_this_month === 'number'
      ? stats.books_this_month
      : recentBooks.length;

  const pagesCount =
    stats.pages_total ?? stats.pages_this_month ?? 0;

  const audioValue = formatAudioValue(stats);

  return (
    <div style={styles.page}>
      <div style={styles.container}>
        <div style={styles.headerCard}>
          <div style={styles.topRow}>
            <div style={styles.titleWrap}>
              <div style={styles.logo}>📚</div>
              <div>
                <h3 style={styles.title}>Я читаю</h3>
              </div>
            </div>

            <button style={styles.logoutButton} onClick={onLogout}>
              Выйти
            </button>
          </div>

          <div style={styles.profileCard}>
            {vkUser?.photo_100 ? (
              <img
                src={vkUser.photo_100}
                alt={displayName}
                style={styles.avatar}
              />
            ) : (
              <div style={styles.avatarFallback}>
                {getInitials(vkUser, data)}
              </div>
            )}

            <div>
              <p style={styles.profileName}>{displayName}</p>
              <p style={styles.profileMeta}>Аккаунт: {accountName}</p>
            </div>
          </div>
        </div>

        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>Книги</h2>

          {books.length ? (
            <div style={styles.booksGrid}>
              {books.map((book, index) => {
                const isReading = book.shelf_status === 'reading';
                const progressValue =
                  typeof book.progress_percent === 'number'
                    ? Math.round(book.progress_percent)
                    : null;

                return (
                  <div
                    key={`${book.shelf_status}-${book.id ?? index}`}
                    style={styles.bookCard}
                  >
                    <div style={styles.coverWrap}>
                      <div
                        style={{
                          ...styles.badge,
                          ...(isReading ? styles.badgeReading : styles.badgeFinished),
                        }}
                      >
                        {isReading ? 'Читаю сейчас' : 'Прочитано'}
                      </div>

                      {isReading && progressValue !== null ? (
                        <div style={styles.progressBadge}>
                          {progressValue}%
                        </div>
                      ) : null}

                      {renderCover(book.cover_url, book.title, styles)}
                    </div>

                    <div>
                      <p style={styles.bookTitle}>
                        {book.title || 'Без названия'}
                      </p>
                      <p style={styles.bookAuthors}>
                        {Array.isArray(book.authors) && book.authors.length
                          ? book.authors.join(', ')
                          : 'Автор не указан'}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div style={styles.emptyCard}>Пока на полке нет книг.</div>
          )}
        </section>

        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>Статистика за месяц</h2>

          <div style={styles.statsGrid}>
            <StatCard
              label="Прочитано книг"
              value={booksCount}
              styles={styles}
            />
            <StatCard
              label="Прочитано страниц"
              value={formatPagesValue(pagesCount)}
              styles={styles}
            />
            <StatCard
              label="Прослушано в аудио"
              value={audioValue}
              styles={styles}
            />
          </div>
        </section>
      </div>
    </div>
  );
};