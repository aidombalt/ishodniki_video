# v3: перемонтаж под новую редакцию решения
Восстановление: распаковать `../archive/celevye_vznosy_project.zip.*` (cat > p.zip; unzip), затем поверх скопировать
`v3/src/*` в `src/`, `v3/input/voice/*` в `input/voice/` (02 и 14 заменяются новыми), `v3/input/docs/*` в `input/docs/`.
Дальше: `python3 src/prepare.py`; план на ровной сетке — `python3 src/plan_grid.py 107`; после получения трека — положить его в `input/music/music.mp3` и собирать по README проекта.
Заказ музыки — `music_order_v3.md`.
