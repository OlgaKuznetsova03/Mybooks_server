import { createRoot } from 'react-dom/client';
import vkBridge from '@vkontakte/vk-bridge';

import { AppConfig } from './AppConfig';
import { hydrateStorageFromBridge } from './utils/storage';

async function bootstrap() {
  try {
    await vkBridge.send('VKWebAppInit');
  } catch {
    // ignore bridge init error in non-VK/dev contexts
  }

  await hydrateStorageFromBridge();

  createRoot(document.getElementById('root')).render(<AppConfig />);

  if (import.meta.env.MODE === 'development') {
    import('./eruda.js');
  }
}

void bootstrap();