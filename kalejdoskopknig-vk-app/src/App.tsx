import '@vkontakte/vkui/dist/vkui.css';

import { AdaptivityProvider, AppRoot, ConfigProvider, Panel, SplitCol, SplitLayout, View } from '@vkontakte/vkui';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import { AuthProvider, useAuth } from './auth/AuthContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { HomePage } from './pages/HomePage/HomePage';
import { LoginPage } from './pages/LoginPage/LoginPage';
import { RegisterPage } from './pages/LoginPage/RegisterPage';

const AppRoutes = () => {
  const { user, loading } = useAuth();

if (loading) {
    return null;
  }

return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <LoginPage />} />
      <Route path="/register" element={user ? <Navigate to="/" replace /> : <RegisterPage />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <HomePage />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to={user ? '/' : '/login'} replace />} />
    </Routes>
  );
};

export default function App() {

  return (
    <ConfigProvider>
      <AdaptivityProvider>
        <AppRoot>
          <SplitLayout>
            <SplitCol autoSpaced width="100%" maxWidth="560px">
              <View activePanel="main">
                <Panel id="main">
                  <AuthProvider>
                    <BrowserRouter>
                      <AppRoutes />
                    </BrowserRouter>
                  </AuthProvider>
                </Panel>
              </View>

            </SplitCol>
          </SplitLayout>
        </AppRoot>
      </AdaptivityProvider>
    </ConfigProvider>
  );
}
