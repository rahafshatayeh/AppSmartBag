import AsyncStorage from '@react-native-async-storage/async-storage';

const KEY = 'bag_logs';

export async function getLogs() {
  try {
    return JSON.parse((await AsyncStorage.getItem(KEY)) || '[]');
  } catch {
    return [];
  }
}

export async function addLog(action, who) {
  const logs = await getLogs();
  const entry = {
    id: String(Date.now()),
    action,
    who: who || '',
    time: new Date().toISOString(),
  };
  await AsyncStorage.setItem(KEY, JSON.stringify([entry, ...logs].slice(0, 50)));
}

export async function clearLogs() {
  await AsyncStorage.removeItem(KEY);
}
