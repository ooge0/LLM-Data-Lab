.. _09-neo4j-advanced-analysis:

Neo4j: реализованная аналитика и расширенное обнаружение аномалий
==================================================================

Этот документ разделён на две части. Первая — теоретический фундамент:
property graph, Neo4j GDS, structural embeddings и методы обнаружения аномалий.
Вторая — то, что конкретно реализовано в этом проекте, и то, что ещё не реализовано,
но обосновано теорией.

.. contents::
   :depth: 2
   :local:

----

Часть I. Теория
---------------

.. rubric:: Property Graph и формальная модель

Граф в контексте Neo4j — это **property graph**:

.. math::

   G = (V, E, \lambda_V, \lambda_E, \mu_V, \mu_E)

где :math:`V` — множество узлов, :math:`E \subseteq V \times V` — направленные рёбра,
:math:`\lambda_V : V \to \mathcal{L}` и :math:`\lambda_E : E \to \mathcal{L}` — функции
назначения меток (labels), :math:`\mu_V : V \times K \to \mathbb{R} \cup \text{String}` и
:math:`\mu_E : E \times K \to \mathbb{R} \cup \text{String}` — функции свойств (properties).

**Property graph vs. RDF.** В RDF граф — это тройки ``(subject, predicate, object)``; свойства
узла должны быть оформлены как отдельные трипли. В property graph свойство — это просто атрибут
узла или ребра: ``(r:Response {coherence: 0.93, word_count: 412})``. Для аналитики ML-пайплайна
это принципиально: метрики — числа на узлах, а не соседние узлы.

**Bipartite graph** как ключевой паттерн. Граф :math:`G = (U \cup V, E)` двудольный, если
:math:`E \subseteq U \times V` (рёбра только между долями, не внутри). В этом проекте
:math:`Archetype \times Bias` образует взвешенный биpartite граф через ребро ``ASSOCIATED_WITH``.
PageRank на нём технически применим, но результат информативен только если граф неравномерный
по весам рёбер — подробнее в §\ :ref:`09-algo-pagerank`.

.. rubric:: Neo4j GDS: graph catalog и модели выполнения

GDS (Graph Data Science library) работает через понятие **именованного in-memory графа**
(projected graph). Перед запуском любого алгоритма граф проецируется командой
``gds.graph.project(name, nodeLabels, relTypes)``. Проекция живёт в памяти JVM сервера
и не пережива рестарт Neo4j — это ожидаемое поведение, не баг. Следствие для
воспроизводимости: скрипт, который вызывает GDS-алгоритм, обязан сначала проверить
существование проекции (``gds.graph.exists``) и пересоздать её при необходимости.

Модели выполнения алгоритмов:

* ``stream`` — read-only; результат возвращается построчно, ничего не записывается.
* ``mutate`` — результат сохраняется как in-memory свойство узла/ребра в проекции;
  не затрагивает постоянное хранилище Neo4j.
* ``write`` — результат записывается обратно в Neo4j как постоянное свойство.

В этом проекте используются ``stream`` (Leiden, kNN, PageRank) и ``mutate`` (FastRP embeddings).
``write`` не используется — проекция дропается сразу после алгоритма (``try/finally``).

.. rubric:: Random walk и структурные эмбеддинги

Интуиция за методами типа node2vec и FastRP: **два узла структурно похожи, если они часто
попадают в одно "соседство" при случайных обходах графа.** Это аналог word2vec, где слова
похожи по дистрибуции контекстов.

node2vec параметризует random walk через :math:`p` (возврат) и :math:`q` (удаление):
при :math:`q < 1` walk уходит вглубь (DFS-подобно), при :math:`q > 1` — исследует
ближайших соседей (BFS-подобно). Это позволяет настраивать, что считается "похожестью":
структурная эквивалентность (одинаковая роль в графе) vs. гомофилия (нахождение в одном
плотном сообществе).

**FastRP (Fast Random Projection)** — более масштабируемая альтернатива. Ключевая идея:
вместо явных random walks строится многоуровневое усреднение соседских признаков с
случайными проекциями на каждом уровне:

.. math::

   \mathbf{h}_v^{(0)} &= \mathbf{P} \cdot \mathbf{1}_v, \quad \mathbf{P} \in \mathbb{R}^{d \times |V|} \\
   \mathbf{h}_v^{(k)} &= \frac{1}{|N(v)|} \sum_{u \in N(v)} \mathbf{h}_u^{(k-1)} \\
   \mathbf{e}_v       &= \sum_{k=0}^{K} \alpha_k \, \mathbf{h}_v^{(k)}

:math:`\mathbf{P}` — случайная матрица (записи i.i.d. из :math:`\mathcal{N}(0, 1/d)`),
:math:`\alpha_k` — веса уровней. В реализации: :math:`d = 64`, :math:`K` задаётся
``iterationWeights`` (по умолчанию GDS выбирает автоматически).

Зачем эмбеддинги вместо hand-crafted features: **структурное положение узла кодируется
автоматически без знания доменной семантики**. Два узла с разными метками, но
одинаковой топологической ролью окажутся рядом в пространстве :math:`\mathbb{R}^d`.

.. rubric:: Community detection: Louvain и Leiden

**Louvain** оптимизирует модульность :math:`Q` жадно: каждый шаг перемещает узел в
то сообщество, которое даёт наибольший прирост :math:`Q`:

.. math::

   Q = \frac{1}{2m} \sum_{i,j} \left[ A_{ij} - \frac{k_i k_j}{2m} \right] \delta(c_i, c_j)

где :math:`m = \tfrac{1}{2}\sum_{ij} A_{ij}` — суммарный вес рёбер,
:math:`k_i = \sum_j A_{ij}` — взвешенная степень узла :math:`i`,
:math:`\delta(c_i, c_j) = 1` если узлы в одном сообществе.

**Leiden** — улучшение Louvain с гарантией связности каждого сообщества.
Louvain может создавать несвязные сообщества (когда узлы "подтягиваются" к сообществу,
но не связаны с его остальными членами). Leiden добавляет этап refinement:
после каждой итерации разбивает несвязные сообщества на части.

:math:`Q \in (-1, 1)`. Типичные значения для хорошей кластеризации: :math:`Q > 0.3`.
Значение :math:`Q = 0.023` (live result этого проекта) — слабая, но ненулевая структура.
На 25-узловом полносвязном графе с почти равномерными весами это ожидаемо:
алгоритм различает сообщества, но разница между ними невелика.

.. rubric:: Обнаружение аномалий: три семейства методов

**Топологические методы** — аномалия как узел с необычной структурой связей:
высокий/низкий degree, высокая betweenness centrality (узел — мост между сообществами),
низкий clustering coefficient. Работают без label и metric; слабы, если граф плотный
и равномерный (как здесь).

**Атрибутные методы** — аномалия как узел, чьи numeric properties отклоняются
от нормы. Формально для одного узла :math:`i` и одной метрики :math:`f`:

.. math::

   z_{i,f} = \frac{x_{i,f} - \mu_f}{\sigma_f}

Глобальная :math:`\mu_f` и :math:`\sigma_f` по всем узлам одного типа.
Узел аномален, если :math:`|z_{i,f}| > \theta` для нескольких метрик.

**Local Outlier Factor (LOF)** обобщает идею: аномальность узла определяется
отношением его локальной плотности к плотности его соседей. LOF хорошо работает на
евклидовых данных, но на малых графах с неравномерными соседствами результат нестабилен.

**Community-relative Z-score (комбинированный)** — аномалия определяется относительно
сообщества, а не всего графа. Для узла :math:`i`, принадлежащего сообществу :math:`c(i)`:

.. math::

   z_{i,f}^{(c)} = \frac{x_{i,f} - \mu_{c(i),f}}{\sigma_{c(i),f}}

Интегральный anomaly score:

.. math::

   A_i = \frac{1}{|F|} \sum_{f \in F} \left| z_{i,f}^{(c)} \right|

Это практически применимый baseline для данного проекта: узлы-аномалии интерпретируемы
(«archetype X ведёт себя не как остальные члены своего сообщества по метрике coherence»),
а не просто «выброс по embedding-расстоянию».

.. rubric:: GraphQL поверх Neo4j

GraphQL — это язык запросов и тип-система для API. ``@neo4j/graphql`` генерирует
GraphQL-резолверы автоматически из аннотированных type-определений:

.. code-block:: graphql

   type Response @node {
     responseId: String!
     coherence:  Float
     generatedBy: [Model!]! @relationship(type: "GENERATED_BY", direction: OUT)
   }

По этому определению библиотека автоматически создаёт Cypher-запрос для резолвера
``response(where: { coherence_GT: 0.9 })``. Это **дополняет**, а не заменяет прямой
Cypher: GDS-алгоритмы и bulk UNWIND ingestion остаются в ``Neo4jGraphRepo``; GraphQL
даёт типизированный read-интерфейс для ad-hoc запросов из FastAPI-слоя.

----

Часть II. Реализованная аналитика
----------------------------------

.. rubric:: Граф отказов: схема данных

Реализация: ``core/adapters/neo4j_repo.py``, интерфейс: ``core/domain/interfaces.py``
(``GraphRepository`` protocol).

**Узлы:**

.. list-table::
   :widths: 18 35 47
   :header-rows: 1

   * - Label
     - Ключевые свойства
     - Что кодирует
   * - ``Response``
     - ``response_id``, ``word_count``, ``duration_ms``
     - Один сгенерированный ответ модели
   * - ``Archetype``
     - ``name``
     - Поведенческий архетип (Neutral, Expressive, …)
   * - ``Bias``
     - ``name``
     - Стилистический тег (formal, toxic, …)
   * - ``Model``
     - ``name``
     - Ollama-модель (student или teacher)
   * - ``Run``
     - ``run_id``
     - Запуск эксперимента
   * - ``CascadeStage``
     - ``name`` (Layer0/Layer1/Layer2/Judge)
     - Уровень validation cascade
   * - ``CascadeOutcome``
     - ``stage``, ``result``
     - Конкретный исход для одного ответа на одном уровне
   * - ``KnowledgeChunk``
     - ``archetype``, ``category``
     - Фрагмент RAG-базы знаний

**Рёбра:**

.. list-table::
   :widths: 22 28 25 25
   :header-rows: 1

   * - Тип
     - От → До
     - Свойства
     - Когда создаётся
   * - ``IN_RUN``
     - Response → Run
     - —
     - При каждом sync
   * - ``CONDITIONED_ON``
     - Response → Archetype/Bias
     - —
     - При каждом sync
   * - ``GENERATED_BY``
     - Response → Model (student)
     - —
     - При каждом sync
   * - ``JUDGED_BY``
     - Response → Model (teacher)
     - —
     - Только если Judge сработал
   * - ``REACHED``
     - Response → CascadeOutcome
     - ``score``, ``confidence``
     - По каждому достигнутому уровню
   * - ``PART_OF``
     - CascadeOutcome → CascadeStage
     - —
     - При каждом sync
   * - ``PRECEDES``
     - CascadeStage → CascadeStage
     - —
     - Bootstrap (один раз)
   * - ``RETRIEVED``
     - Response → KnowledgeChunk
     - —
     - Только при RAG enabled
   * - ``CO_OCCURS_WITH``
     - any → any
     - ``weight``
     - Материализуется по требованию
   * - ``ASSOCIATED_WITH``
     - Archetype → Bias
     - ``weight``
     - Материализуется для PageRank

Вес ``CO_OCCURS_WITH`` — количество ``Response``-узлов, через которые два узла
оказались в одном соседстве:

.. math::

   w(a, b) = \bigl|\{ r \in \mathcal{R} \mid a \in N(r) \land b \in N(r) \}\bigr|

где :math:`N(r)` — все узлы, с которыми :math:`r` связан через
``CONDITIONED_ON | GENERATED_BY | REACHED``.

.. rubric:: Структура pipeline в графе

``PRECEDES``-рёбра кодируют порядок уровней: Layer0 → Layer1 → Layer2 → Judge.
Это позволяет Cypher-запросу «найти последний достигнутый уровень» без
захардкоженного ранга на стороне приложения:

.. code-block:: cypher

   MATCH (r)-[:REACHED]->(o)-[:PART_OF]->(s)
   WHERE NOT EXISTS {
     MATCH (s)-[:PRECEDES]->(:CascadeStage)<-[:PART_OF]-(:CascadeOutcome)<-[:REACHED]-(r)
   }
   RETURN o.stage AS terminal_stage, o.result AS terminal_result, count(r) AS n

Известная семантическая тонкость: Layer 2 (NLI-проверка) запускается до echo-ветки
Layer 1 и является безусловным по echo-статусу, поэтому ответ может иметь
``layer2_checked=True`` при echo-отклонении на Layer 1. В ``PRECEDES``-обходе
это выглядит как «Layer 2 — терминальный уровень», хотя реальный вердикт вынесен
на Layer 1. Корректный запрос (см. ``_ROOT_CAUSE_TERMINAL_STAGE_CYPHER``) учитывает
это через ``NOT EXISTS``-субзапрос.

.. _09-algo-pagerank:

.. rubric:: Weighted PageRank (Archetype–Bias биpartite граф)

Алгоритм определяет "центральность" узла через рекурсивную передачу веса:

.. math::

   PR(u) = \frac{1-d}{|V|} + d \sum_{v \to u} \frac{w(v,u)}{W(v)} \cdot PR(v)

где :math:`W(v) = \sum_{e \ni v} w(e)` — взвешенная степень узла,
:math:`d = 0.85` — damping factor (вероятность продолжить переход, не "прыгать"
в случайный узел).

Реализация: ``Neo4jGraphRepo.archetype_bias_pagerank()``. Проекция:
``['Archetype', 'Bias']`` с ребром ``ASSOCIATED_WITH`` (вес = количество уникальных
``Response``-узлов, conditioned on этой паре).

**Два исправленных бага** (документированы в :doc:`07-knowledge-graph-results`):

1. *Single-label projection с нулевыми рёбрами.* Исходная проекция включала только
   ``Archetype``-узлы. Все рёбра ``ASSOCIATED_WITH`` ведут к ``Bias``-узлам — они
   не попали в проекцию. Нулевой граф: каждый узел получает baseline
   :math:`PR = (1-d)/|V| = 0.15`. Итог: все архетипы — одинаковые.

2. *Неравномерный K_{5,6} всё равно симметричен.* Полный биpartite граф
   :math:`K_{p,q}` с равными весами на рёбрах даёт одинаковый PageRank для всех
   узлов одной доли — это математически доказуемо из симметрии матрицы переходов.
   Исправлено добавлением ``SET co.weight = count(DISTINCT r)`` и
   удалением рёбер с ``co.weight IS NULL`` (NaN-ловушка GDS).

.. rubric:: Leiden Community Detection

Реализация: ``Neo4jGraphRepo.behavioral_communities()``. Проекция включает все
«не-Response» узлы (Archetype, Bias, Model, CascadeOutcome) с ребром
``CO_OCCURS_WITH``.

Алгоритм оптимизирует модульность :math:`Q` (формула в Части I). Live result:
:math:`Q = 0.023`, 4 сообщества. Ключевые группы:

* qwen + tinyllama + Neutral + Detached + Expressive → одно сообщество.
* personalization bias — изолирован (подтверждено независимо через kNN).

Низкое :math:`Q` закономерно: граф из 25 узлов с balanced factorial дизайном
(каждая архетип-модель пара появляется примерно одинаково) производит
близкий к равномерному граф co-occurrence.

.. rubric:: FastRP Embeddings + kNN Structural Similarity

Реализация: ``Neo4jGraphRepo.structural_similarity()``. Два шага:

1. ``gds.fastRP.mutate`` (``embeddingDimension: 64``) — пишет 64-мерные эмбеддинги
   в in-memory граф (``mutate``, не ``write``).
2. ``gds.knn.stream`` (``topK: 3``) — для каждого узла находит 3 ближайших по
   косинусному сходству:

.. math::

   \text{sim}(a, b) = \frac{\mathbf{e}_a \cdot \mathbf{e}_b}{\|\mathbf{e}_a\| \cdot \|\mathbf{e}_b\|}

**Почему ``gds.knn``, а не ``gds.nodeSimilarity``:** ``nodeSimilarity`` вычисляет
Jaccard/overlap по общим *соседям* (топологическая похожесть), не по embedding-векторам.
``knn`` — ближайшие соседи именно по числовым свойствам узла (embedding).

Live results:

* Neutral/Detached/Expressive + qwen/tinyllama: :math:`\text{sim} \approx 0.9999` —
  та же группа, что Leiden поместил в одно сообщество (конвергентное свидетельство).
* Наиболее аномальный узел: ``personalization`` bias, best-match sim = 0.0.

.. rubric:: Root-cause Cypher-запросы

Три параметризованных шаблона в ``_ROOT_CAUSE_*_CYPHER``:

**Echo rejections by model** — какие модели чаще всего echo-отклоняются на Layer 1:

.. code-block:: cypher

   MATCH (r:Response)-[:GENERATED_BY]->(m:Model),
         (r)-[:REACHED]->(:CascadeOutcome {stage:"Layer1", result:"ECHO"})
   RETURN m.name AS model, count(r) AS echo_count ORDER BY echo_count DESC

Live result (run ``run-1787604530235``, 500 responses): mistral 27 echo-отклонений,
qwen 12 — mistral вдвое хуже.

**Terminal stage by archetype** — на каком уровне каскада обычно "заканчиваются" ответы
заданного архетипа. Использует ``PRECEDES``-граф + ``NOT EXISTS``-субзапрос (см. выше).

**RAG chunks linked to echo** — какие фрагменты RAG-базы чаще всего
ассоциированы с echo-отклонениями:

.. code-block:: cypher

   MATCH (c:KnowledgeChunk)<-[:RETRIEVED]-(r:Response)
         -[:REACHED]->(:CascadeOutcome {stage:"Layer1", result:"ECHO"})
   RETURN c.archetype, c.category, count(r) AS echo_count ORDER BY echo_count DESC

Live result: ``paranoid | Behavior`` — 36 echo-отклонений, вдвое больше следующего.
Ответы, получившие этот RAG-фрагмент, непропорционально часто его воспроизводили.

----

Часть III. Расширение: атрибутная аномалистика
-----------------------------------------------

.. rubric:: Что есть в данных, но нет в графе

Каждая запись в JSONL содержит 18+ числовых лингвистических метрик. Ни одна
из них не хранится как свойство ``Response``-узла и не используется для взвешивания рёбер.
Граф «слеп» к качеству и характеру ответа — он знает только факт co-occurrence.

Доступные поля (из ``results/lab_experiment_results/lab_export_run-1788638565480.jsonl``):

.. code-block:: text

   corrected_ttr      — Type-Token Ratio (лексическое разнообразие)
   readability_ari    — Automated Readability Index
   coherence          — семантическая связность предложений [0, 1]
   sentiment          — полярность [-1, 1]
   rigidity           — повторяемость конструкций [0, 1]
   cognitive_load     — когнитивная нагрузка
   modality           — частота модальных слов
   zipf_deviation     — отклонение частотного распределения от закона Ципфа
   dependency_distance — средняя синтаксическая дистанция (spaCy)
   lexical_density    — доля контентных слов
   hedge_ratio        — частота хеджирующих выражений
   booster_ratio      — частота усилительных выражений
   semantic_overlap   — семантическое перекрытие с prompt (Layer 1 signal)
   v_confidence       — уверенность judge [0, 1]
   val                — температура (sweep axis, 0.4–1.0)

.. rubric:: Расширение 1. Metric-enriched Response nodes

Добавить в ``_SYNC_FAILURE_MODE_CYPHER`` одну строку:

.. code-block:: cypher

   SET r += $metrics   -- $metrics — dict с 18 числовыми полями

После этого Cypher умеет агрегировать по архетипу напрямую:

.. code-block:: cypher

   MATCH (a:Archetype {name: $arch})<-[:CONDITIONED_ON]-(r:Response)
   RETURN avg(r.coherence)   AS mean_coherence,
          stdev(r.coherence) AS std_coherence,
          avg(r.rigidity)    AS mean_rigidity

Это открывает путь к аномальному скорингу без Python-постобработки.

.. rubric:: Расширение 2. Distribution-aware edge weighting

Заменить сырой count на Jensen–Shannon divergence между распределениями метрик
двух узлов — тогда ``CO_OCCURS_WITH`` кодирует поведенческое расстояние,
а не просто частоту:

.. math::

   w_{\mathrm{JSD}}(a, b) = 1 - \mathrm{JSD}(P_a \| P_b)

.. math::

   \mathrm{JSD}(P \| Q) = \frac{1}{2} D_{\mathrm{KL}}(P \| M) + \frac{1}{2} D_{\mathrm{KL}}(Q \| M),
   \qquad M = \frac{P + Q}{2}

:math:`D_{\mathrm{KL}}(P \| Q) = \sum_x P(x) \log \frac{P(x)}{Q(x)}` — KL-дивергенция.
:math:`\mathrm{JSD} \in [0, 1]` (в отличие от KL-дивергенции, симметрична и ограничена).

Практически: для каждой пары узлов-кандидатов собираются векторы метрик всех их
``Response``-соседей; JSD вычисляется через KDE или гистограмму; результат —
единственное число, которое записывается как ``co.weight`` перед GDS-проекцией.
Никаких изменений в GDS-слое не требуется.

Ключевое улучшение: два узла с одинаковым raw co-occurrence count, но резко разными
metric-профилями, получат разные веса. Leiden на таком графе разделит их.

.. rubric:: Расширение 3. Community-relative anomaly scoring

После Leiden каждый узел получает ``communityId``. Community-relative Z-score:

.. math::

   z_{i,f}^{(c)} = \frac{x_{i,f} - \mu_{c(i),f}}{\sigma_{c(i),f}}

Интегральный anomaly score по всем :math:`|F|` метрикам:

.. math::

   A_i = \frac{1}{|F|} \sum_{f \in F} \left| z_{i,f}^{(c)} \right|

В Cypher (после metric enrichment):

.. code-block:: cypher

   MATCH (r:Response)-[:CONDITIONED_ON]->(a:Archetype)
   WITH a, collect(r.coherence) AS vals
   UNWIND vals AS v
   WITH a, v, avg(vals) AS mu, stdev(vals) AS sigma
   WHERE sigma > 0
   RETURN a.name, (v - mu) / sigma AS z_coherence
   ORDER BY abs(z_coherence) DESC

``sigma > 0`` — защита от единственного ответа в архетипе (иначе деление на ноль).

Интерпретируемость: аномальность конкретна — «архетип Defensive ведёт себя иначе
своего сообщества по coherence на :math:`3.2\sigma`», а не «embedding-расстояние
вышло за порог».

.. rubric:: Расширение 4. Temperature sweep path analysis

Добавить ``NEXT_STEP``-рёбра между ``Response``-узлами с одинаковым
``(archetype, bias, student)`` triple, упорядоченными по ``val`` (температура):

.. math::

   r_i \xrightarrow{\;\text{NEXT\_STEP}\;} r_{i+1}
   \;\Longleftrightarrow\;
   \mathrm{key}(r_i) = \mathrm{key}(r_{i+1})
   \;\land\;
   \mathrm{val}(r_i) < \mathrm{val}(r_{i+1})

Это превращает температурный sweep в явную **последовательность** в графе.
Path-запросы находят дрейф метрик вдоль оси температуры без GROUP BY в Python:

.. code-block:: cypher

   MATCH path = (r0:Response)-[:NEXT_STEP*]->(rN:Response)
   WHERE r0.archetype = 'Defensive' AND r0.bias = 'toxic'
   RETURN [n IN nodes(path) | n.val]       AS temp_axis,
          [n IN nodes(path) | n.coherence] AS coherence_trace

.. rubric:: Расширение 5. GraphQL layer

``@neo4j/graphql`` генерирует типизированный API поверх существующего графа.
Пример: заменить ``/knowledge_graph/echo_by_model`` типизированным запросом
без строкового Cypher в роутере:

.. code-block:: graphql

   query EchoByModel {
     responses(where: {
       cascadeOutcomes_SOME: { stage: "Layer1", result: "ECHO" }
     }) {
       generatedBy { name }
       conditionedOn { name }
     }
   }

Архитектурное замечание: GraphQL — это read-интерфейс. Bulk ingestion (``UNWIND``),
GDS-алгоритмы и materialization-запросы остаются в ``Neo4jGraphRepo``; GraphQL
дополняет, не заменяет Cypher-слой.

----

Ограничения и открытые вопросы
--------------------------------

* :math:`Q = 0.023` — слабая структура при balanced factorial дизайне.
  JSD-взвешивание (Расширение 2) — прямой способ усилить дифференцировку без
  изменения алгоритма.

* Link prediction по топологии — задокументированный dead end (см.
  :doc:`08-graph-representation-learning`): доминирующий сигнал («какая модель»)
  уже полностью содержится в ``Model``-узле, а не в структуре комбо.
  Community-relative anomaly scoring (Расширение 3) нацелен на другой сигнал
  и не имеет той же структурной проблемы.

* Layer 2 (NLI hallucination check) — logging-only, не гейт.
  Добавление в граф ``layer2_contradiction_score`` как свойства ``REACHED``-ребра
  уже реализовано; но порогового значения для аномалий по этой метрике
  нет — первый шаг тот же, что у Layer 1: calibration на реальных данных.

* Расширения 1–4 зависят друг от друга: без metric-enriched nodes (1) нет
  distribution-aware weights (2) и нет community anomaly scoring (3).
  Правильный порядок реализации: 1 → 2 → 3 → 4.
