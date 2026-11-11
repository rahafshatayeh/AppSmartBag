import AsyncStorage from '@react-native-async-storage/async-storage';

const keyForUser = (email) => `smart_bag_packing_list:${email || 'guest'}`;
export async function getPackingItems(email) {
  try { return JSON.parse((await AsyncStorage.getItem(keyForUser(email))) || '[]'); }
  catch { return []; }
}
export async function savePackingItems(items, email) {
  await AsyncStorage.setItem(keyForUser(email), JSON.stringify(items));
}
