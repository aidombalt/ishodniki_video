# Заказ музыки v3 (Suno, Custom Mode, Instrumental — вкл.)

Целевая длительность — **5:40 (340 с)**. Ролик по реальной речи длится 5:30,7. Запас 10 с — на финальный аккорд и подгонку тактами.
Темп **107 BPM**, 4/4, такт 2,243 с — как у прошлого трека, ради преемственности звучания.
Если модель не даёт 5:40 за одну генерацию, продлить тот же трек функцией Extend до 5:40. Не склеивать разные генерации.

## Поле Songtext (только структура, без текста для пения)
```
[Instrumental]
[Target: 5:40, 340 seconds. 107 BPM. 4/4. 148 bars plus ring-out. No vocals.]
[Intro: 9 bars, 0:00-0:21]
[Sparse pulse, soft keys and light percussion, no kick, gentle rise]
[Groove A: 22 bars, 0:21-1:09]
[Kick and snare enter. Steady restrained groove, sparse rounded bass, lots of space for narration]
[Groove B: 49 bars, 1:09-3:00]
[Same groove and harmony. Very light variation every 8 bars. No build-ups, no drops]
[Breakdown: 6 bars, 3:00-3:13]
[Kick out. Soft bass and pads only, calm and neutral]
[Groove return: 7 bars, 3:13-3:29]
[Groove back at the energy of Groove A]
[Calm section: 13 bars, 3:29-3:58]
[Reduced arrangement, light percussion, very soft or no kick, thoughtful]
[Groove C: 21 bars, 3:58-4:45]
[Steady groove, slightly fuller, still restrained]
[Quiet section: 6 bars, 4:45-4:59]
[Hi-hats and kick drop out, soft bass and keys]
[Final groove: 12 bars, 4:59-5:26]
[Opening motif returns, calm and confident]
[Ending: final chord on a downbeat at 5:26, natural ring-out to 5:40]
[Clean ending, no fade-out]
[End]
```

## Поле Style
```
107 BPM, 4/4. Restrained modern electronic funk with a clean midtempo breakbeat groove. Dry controlled kick and snare, precise soft hi-hats, rounded syncopated bass, short clipped synth stabs, sparse percussive keyboard accents. Practical, composed, attentive, lightly upbeat. Consistent neutral energy, polished production, plenty of space for a female spoken Russian voiceover. Strictly instrumental. Stable tempo throughout, clean ending on a final chord. No vocals, vocal chops, spoken words, ukulele, whistling, sentimental piano, ambient wash, melancholy strings, dramatic cinematic build, huge drops, triumphant fanfares or aggressive distortion.
```

## Привязка секций к сценам (для монтажа)
| Такты | Время | Секция | Сцены |
|---|---|---|---|
| 1–9 | 0:00,5–0:20,7 | Интро | логотип, 01 |
| 10–31 | 0:20,7–1:09,5 | Грув A | 02 (вопросы, формула, 6 платежей), 03 (пример 41 м²) |
| 32–80 | 1:09,5–2:59,9 | Грув B | 04–07 (карточки работ и расчёты) |
| 81–86 | 2:59,9–3:13,3 | Брейк | 08 (условие по площадкам) |
| 87–93 | 3:13,3–3:29,0 | Возврат грува | 09a (итог) |
| 94–106 | 3:29,0–3:58,2 | Спокойная секция | 09n (калькулятор), 09r (округление) |
| 107–127 | 3:58,2–4:45,3 | Грув C | 09b (распределители), 10, 11 |
| 128–133 | 4:45,3–4:58,8 | Тихая секция | 12 (очная часть) |
| 134–145 | 4:58,8–5:25,7 | Финальный грув | 13, 15 (призыв) |
| 146 → | 5:25,7–5:40 | Финальный аккорд, затухание | финальная карточка |

Реальный темп и сильные доли измеряются по готовому треку. Склейки сцен ставятся на его доли. Секции подгоняются целыми тактами или полутактами внутри однородных участков.
