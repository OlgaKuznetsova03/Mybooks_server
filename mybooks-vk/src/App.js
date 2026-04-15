import { useVkUser } from './hooks/useVkUser';
import { useShelf } from './hooks/useShelf';
import { ShelfView } from './views/ShelfView';

function App() {
  const { user, loading, error, needsLinking } = useVkUser();
  const {
    data: shelfData,
    loading: shelfLoading,
    error: shelfError,
  } = useShelf(Boolean(user) && !needsLinking);

if (loading || shelfLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        Загрузка...
      </div>
    );
  }

  if (error || shelfError) {
    return (
      <div style={{ padding: 20 }}>
        <h3>Ошибка</h3>
        <p>{error || shelfError?.message}</p>
        <button onClick={() => window.location.reload()}>Повторить</button>
      </div>
    );
  }

  if (needsLinking) {
    return (
      <div style={{ padding: 20 }}>
        <h3>Требуется привязка VK аккаунта</h3>
        <p>Пожалуйста, войдите с email и паролем для привязки VK аккаунта.</p>
      </div>
    );
  }

  if (user && shelfData) {
    return <ShelfView data={shelfData} vkUser={user} />;
  }

  return null;
}

  export default App;