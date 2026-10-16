# v3: перемонтаж под новую редакцию решения
Восстановление: распаковать `../archive/celevye_vznosy_project.zip.*` (cat > p.zip; unzip), затем поверх скопировать
`v3/src/*` в `src/`, `v3/input/voice/*` в `input/voice/` (02 и 14 заменяются новыми), `v3/input/docs/*` в `input/docs/`.
Дальше: `python3 src/prepare.py`; план на ровной сетке — `python3 src/plan_grid.py 107`; после получения трека — положить его в `input/music/music.mp3` и собирать по README проекта.
Заказ музыки — `music_order_v3.md`.

## v4: блок «Зачем нужны работы», без сцены 08
Новые входные файлы: `input/voice/01z.mp3`, `input/photos/` (№ 1, 20, 26 в кадре; 2, 10, 11 в запасе), `input/music/music.mp3` (трек v3).
Скопировать их в проект вместе с `src/*`, затем собрать по README проекта. Заказ и раскладка — `input/docs/Zakaz_ozvuchki_v4.md`.
