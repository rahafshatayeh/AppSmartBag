import AsyncStorage from '@react-native-async-storage/async-storage';

const CONFIG_KEY = 'bag_config';
export const DEFAULT_CONFIG = { ip: '192.168.1.50', token: 'change-me-123' };
export async function getConfig() {
  try { const raw = await AsyncStorage.getItem(CONFIG_KEY); return raw ? { ...DEFAULT_CONFIG, ...JSON.parse(raw) } : DEFAULT_CONFIG; }
  catch { return DEFAULT_CONFIG; }
}
export async function saveConfig(config) { await AsyncStorage.setItem(CONFIG_KEY, JSON.stringify(config)); }

async function request(path, method = 'GET') {
  const { ip, token } = await getConfig();
  const host = String(ip || '').trim().replace(/^https?:\/\//, '').replace(/\/.*$/, '').replace(/:\d+$/, '');
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(`http://${host}:5000${path}`, { method, headers: { 'X-Token': token }, signal: controller.signal });
    if (response.status === 401) throw new Error('badToken');
    if (!response.ok) {
      let message = 'bagError';
      try { const data = await response.json(); if (data && data.error) message = data.error; } catch {}
      throw new Error(message);
    }
    return await response.json();
  } catch (error) {
    if (error.name === 'AbortError' || /cancel|abort/i.test(String(error.message))) throw new Error('timeout');
    if (String(error.message).includes('Network request failed')) throw new Error('networkFailure');
    throw error;
  } finally { clearTimeout(timer); }
}
export const getStatus = () => request('/info');
export const getFollowInfo = () => request('/info');
export const startFaceRegistration = () => request('/register');
export const unlockBag = () => request('/unlock', 'POST');
export const lockBag = () => request('/lock', 'POST');
// ---- الميزان ----
export const getWeight = () => request('/weight');
export const setWeightLimit = (limitKg) => request(`/weight_cfg?bag=0&limit=${encodeURIComponent(limitKg)}`);