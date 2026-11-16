// بث كاميرا الرازبيري المباشر — بدون أي مكتبة إضافية
// بيطلب /snapshot من الرازبيري صورة ورا صورة بأسرع ما يقدر،
// والصورة القديمة بتضل ظاهرة لحد ما الجديدة تخلص تحميل (ما في رمشة ولا شاشة سودا).
import { useEffect, useRef, useState } from 'react';
import { View, Image, Text, StyleSheet, ActivityIndicator } from 'react-native';
import { useIsFocused } from '@react-navigation/native';
import { getConfig } from '../services/api';

const hostOf = (ip) => String(ip || '').trim().replace(/^https?:\/\//, '').replace(/\/.*$/, '').replace(/:\d+$/, '');

export default function LiveCamera({ height = 245, style }) {
  const isFocused = useIsFocused();
  const [base, setBase] = useState(null);      // http://IP:5000/snapshot
  const [shown, setShown] = useState(null);    // الصورة الظاهرة
  const [next, setNext] = useState(null);      // الصورة اللي عم تتحمّل (مخفية)
  const [status, setStatus] = useState('connecting'); // connecting | live | error
  const n = useRef(0);
  const fails = useRef(0);
  const timer = useRef(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    getConfig().then((c) => { if (alive.current) setBase(`http://${hostOf(c.ip)}:5000/snapshot`); });
    return () => { alive.current = false; clearTimeout(timer.current); };
  }, []);

  const requestNext = (delay = 0) => {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      if (!alive.current || !base) return;
      n.current += 1;
      setNext({ uri: `${base}?f=${n.current}` });
    }, delay);
  };

  // بلّش البث لما الشاشة تكون ظاهرة، ووقّفه لما تطلعي منها
  useEffect(() => {
    if (base && isFocused) requestNext(0);
    else clearTimeout(timer.current);
    return () => clearTimeout(timer.current);
  }, [base, isFocused]);

  const onLoad = () => {
    fails.current = 0;
    setShown(next);
    setStatus('live');
    requestNext(0);                 // الصورة الجاية فوراً = أسرع بث ممكن
  };
  const onError = () => {
    fails.current += 1;
    if (fails.current >= 3) setStatus('error');
    requestNext(Math.min(2000, 300 * fails.current));   // بيرجع يحاول لحاله
  };

  return <View style={[s.frame, { height }, style]}>
    {shown && <Image source={shown} resizeMode="contain" fadeDuration={0} style={[s.img, { height }]} />}
    {next && isFocused && <Image key={next.uri} source={next} resizeMode="contain" fadeDuration={0}
      style={[s.img, s.hidden, { height }]} onLoad={onLoad} onError={onError} />}

    {status !== 'live' && <View pointerEvents="none" style={s.overlay}>
      {status === 'connecting' ? <ActivityIndicator color="#fff" /> : null}
      <Text style={s.overlayText}>{status === 'connecting' ? 'جاري الاتصال بكاميرا الحقيبة…' : 'الكاميرا مش واصلة — بحاول من جديد…'}</Text>
      {status === 'error' && <Text style={s.small}>{base}</Text>}
    </View>}

    <View pointerEvents="none" style={s.badge}>
      <View style={[s.dot, { backgroundColor: status === 'live' ? '#6FE0A2' : '#FFC56B' }]} />
      <Text style={s.badgeText}>{status === 'live' ? 'بث مباشر' : 'جاري الاتصال'}</Text>
    </View>
  </View>;
}

const s = StyleSheet.create({
  frame: { width: '100%', borderRadius: 23, overflow: 'hidden', backgroundColor: '#17211E' },
  img: { position: 'absolute', top: 0, left: 0, width: '100%' },
  hidden: { opacity: 0.01 },
  overlay: { ...StyleSheet.absoluteFillObject, alignItems: 'center', justifyContent: 'center', gap: 8, padding: 16 },
  overlayText: { color: '#fff', fontSize: 13, fontWeight: '700', textAlign: 'center' },
  small: { color: '#9fb3ad', fontSize: 11 },
  badge: { position: 'absolute', top: 11, right: 11, flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: 'rgba(20,35,31,0.72)', paddingHorizontal: 10, paddingVertical: 7, borderRadius: 16 },
  dot: { width: 7, height: 7, borderRadius: 4 },
  badgeText: { color: '#fff', fontSize: 10, fontWeight: '800' },
});