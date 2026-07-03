using System.Collections.Generic;
using System.Text.RegularExpressions;
using UnityEngine;
using UnityEngine.UI;
using TMPro;
using Newtonsoft.Json.Linq;
#if UNITY_EDITOR
using UnityEditor;
#endif

namespace PaperCave
{
    /// <summary>
    /// Versão definitiva e dinâmica da cena PaperCave_Cards_3D.
    /// Lê um manifest.json de um paper (formato V2 "units" OU legado "gameObjects")
    /// e instancia, em runtime, um card por unidade reaproveitando o prefab CardBase
    /// (mesma anatomia da cena feita à mão: Card3D + CardClickVFXBridge + CardContentFitter).
    ///
    /// Regras pedidas:
    ///  - Todo card dispara o VFX de abertura (CardClickVFXBridge -> VFXManager.PlayEffectAt).
    ///  - Card de tabela ganha uma tabela INTERATIVA (TableBuilder + TableRowHover) que segue o card.
    ///  - Card de imagem injeta a figura no Figure_Box; o CardContentFitter detecta portrait/landscape
    ///    e, em landscape, o card se "deita" na horizontal (largura cresce até maxLandscapeWidth).
    /// </summary>
    public class PaperCaveManifestLoader : MonoBehaviour
    {
        [Header("Fonte do paper")]
        [Tooltip("Pasta do paper em Assets/PaperCaveData/<id>. O manifest é lido de <pasta>/manifest.json e as figuras de <pasta>/images/.")]
        public string paperName = "emotional_tissue_visual_states";

        private string paperDataFolder =>
            $"Assets/PaperCaveData/{paperName}";

        [Tooltip("Opcional: arraste um manifest.json específico. Se preenchido, tem prioridade sobre paperDataFolder.")]
        public TextAsset manifestOverride;

        [Header("Prefabs e referências de cena")]
        public GameObject cardBasePrefab;
        public VFXManager vfxManager;
        [Tooltip("Índice do efeito no VFXManager disparado ao abrir qualquer card.")]
        public int openVfxIndex = 0;
        [Tooltip("Opcional: prefab de título (TMP). Se vazio, o título é ignorado.")]
        public GameObject titlePrefab;
        public Transform titleAnchor;

        [Header("Layout (leque centrado)")]
        public Vector3 primaryPosition = new Vector3(0f, 0.4f, 0f);
        public int perRow = 3;
        public float xStep = 2.1f;
        public float yStep = 1.85f;
        public float fanRotationPerX = 5f;

        [Header("Empilhamento por tag (deck)")]
        [Tooltip("Profundidade (z) entre cartas empilhadas da mesma tag.")]
        public float stackDepthStep = 0.05f;
        [Tooltip("Leque: rotacao Z (graus) por carta no deck.")]
        public float stackRotZStep = 0f;
        [Tooltip("Deslocamento XY por carta no deck (para nao coincidirem exatamente).")]
        public Vector2 stackPosStep = new Vector2(0.06f, 0.06f);

        [Header("Tabela (follower world-space)")]
        public float tableWorldWidth = 2.4f;
        public Vector3 tableLocalOffset = new Vector3(0f, -0.15f, -0.7f);

        [Header("Execução")]
        public bool buildOnStart = true;

        private readonly List<GameObject> _spawned = new List<GameObject>();

        private enum Kind { Text, Image, Table }

        private class CardSpec
        {
            public string title = "";
            public string summary = "";      // texto curto (collapsed)
            public string description = "";  // texto longo (expanded)
            public string caption = "";
            public string category = "";
            public Color color = new Color(0f, 0.83f, 1f, 1f);
            public Kind kind = Kind.Text;
            public List<string> imageRefs = new List<string>();
            public List<string> headers;
            public List<List<string>> rows;
            public bool primary;
        }

        void Start()
        {
            paperName = PlayerPrefs.GetString("SelectedPaper", paperName);

            if (buildOnStart)
                Build();
        }

        public void LoadPaper(string newPaperName)
        {
            paperName = newPaperName;
            Build();
        }

        [ContextMenu("Build Cards From Manifest")]
        public void Build()
        {
            Clear();

            string json = LoadManifestJson();
            if (string.IsNullOrWhiteSpace(json))
            {
                Debug.LogError("[PaperCaveManifestLoader] Manifest vazio ou não encontrado.");
                return;
            }

            JObject root;
            try { root = JObject.Parse(json); }
            catch (System.Exception e)
            {
                Debug.LogError("[PaperCaveManifestLoader] Falha ao parsear manifest: " + e.Message);
                return;
            }

            string paperTitle = (string)root["paperTitle"] ?? "";
            List<CardSpec> specs = root["units"] != null ? ParseV2(root)
                                 : root["gameObjects"] != null ? ParseLegacy(root)
                                 : null;

            if (specs == null || specs.Count == 0)
            {
                Debug.LogWarning("[PaperCaveManifestLoader] Nenhuma unidade encontrada no manifest.");
                return;
            }

            if (cardBasePrefab == null)
            {
                Debug.LogError("[PaperCaveManifestLoader] cardBasePrefab não atribuído.");
                return;
            }

            specs = MergeGerminatedImages(specs);

            SpawnTitle(paperTitle);

            // Garante que o card primário fique no índice 0 do layout.
            // Agrupa por tag (categoria) preservando a ordem de aparicao no paper.
            var groupOrder = new List<string>();
            var groups = new Dictionary<string, List<CardSpec>>();
            foreach (var s in specs)
            {
                string key = (s.category ?? "").Trim().ToLowerInvariant();
                if (!groups.ContainsKey(key)) { groups[key] = new List<CardSpec>(); groupOrder.Add(key); }
                groups[key].Add(s);
            }
            // O grupo que contem o card primario vai para o slot primario (indice 0).
            for (int gi = 0; gi < groupOrder.Count; gi++)
            {
                bool hasPrimary = false;
                foreach (var s in groups[groupOrder[gi]]) if (s.primary) { hasPrimary = true; break; }
                if (hasPrimary) { var k = groupOrder[gi]; groupOrder.RemoveAt(gi); groupOrder.Insert(0, k); break; }
            }

            int globalIndex = 0;
            for (int gi = 0; gi < groupOrder.Count; gi++)
            {
                Vector3 basePos; float baseRotY;
                ComputeLayout(gi, groupOrder.Count, out basePos, out baseRotY);
                var stack = groups[groupOrder[gi]];
                for (int j = 0; j < stack.Count; j++)
                {
                    // Primeira carta do paper na frente (z menor); demais empurradas para tras + leque.
                    Vector3 pos = basePos + new Vector3(stackPosStep.x * j, stackPosStep.y * j, stackDepthStep * j);
                    float rotZ = StackRotZ(j);
                    BuildCard(stack[j], pos, baseRotY, rotZ, globalIndex);
                    globalIndex++;
                }
            }

            Debug.Log($"[PaperCaveManifestLoader] {specs.Count} card(s) instanciados para '{paperTitle}'.");
        }

        [ContextMenu("Clear")]
        public void Clear()
        {
            foreach (var go in _spawned)
            {
                if (go == null) continue;
#if UNITY_EDITOR
                if (!Application.isPlaying) DestroyImmediate(go); else Destroy(go);
#else
                Destroy(go);
#endif
            }
            _spawned.Clear();
        }

        // ------------------------------------------------------------------ load

        private string LoadManifestJson()
        {
            if (manifestOverride != null) return manifestOverride.text;
            string path = paperDataFolder.TrimEnd('/') + "/manifest.json";
#if UNITY_EDITOR
            var ta = AssetDatabase.LoadAssetAtPath<TextAsset>(path);
            if (ta != null) return ta.text;
#endif
            if (System.IO.File.Exists(path)) return System.IO.File.ReadAllText(path);
            return null;
        }

        // ------------------------------------------------------------------ parse V2

        private List<CardSpec> ParseV2(JObject root)
        {
            var list = new List<CardSpec>();
            foreach (var u in root["units"])
            {
                var spec = new CardSpec();
                spec.title = (string)u["title"] ?? "";
                spec.category = (string)u["category"] ?? "";
                spec.summary = (string)u["summary"] ?? "";
                spec.primary = ((string)u["priority"] ?? "").ToLower() == "primary";

                var content = u["content"];
                if (content != null)
                {
                    spec.description = (string)content["description"] ?? "";
                    spec.caption = (string)content["caption"] ?? "";
                }
                if (string.IsNullOrEmpty(spec.summary)) spec.summary = Shorten(spec.description, 150);

                spec.color = ParseColor((string)(u["styleHint"]?["categoryColor"]), spec.category);

                string contentType = ((string)u["contentType"] ?? "").ToLower();
                string assetRef = (string)(content?["assetReference"]);
                var data = content?["data"];
                if (data != null && data.Type == Newtonsoft.Json.Linq.JTokenType.Null) data = null;

                if (contentType == "table" || data != null)
                {
                    spec.kind = Kind.Table;
                    ReadV2Table(data, spec);
                }
                else if (contentType == "figure" || !string.IsNullOrEmpty(assetRef))
                {
                    spec.kind = Kind.Image;
                    if (!string.IsNullOrEmpty(assetRef)) spec.imageRefs.Add(assetRef);
                }
                else
                {
                    spec.kind = Kind.Text;
                }
                list.Add(spec);
            }
            return list;
        }

        private void ReadV2Table(JToken data, CardSpec spec)
        {
            spec.headers = new List<string>();
            spec.rows = new List<List<string>>();
            if (data == null) return;
            var cols = data["columns"] as JArray;
            if (cols != null) foreach (var c in cols) spec.headers.Add((string)c);
            var rows = data["rows"] as JArray;
            if (rows != null)
            {
                foreach (var r in rows)
                {
                    var cells = new List<string>();
                    if (r is JArray ra) foreach (var c in ra) cells.Add((string)c);
                    spec.rows.Add(cells);
                }
            }
        }

        // ------------------------------------------------------------------ parse legacy

        private List<CardSpec> ParseLegacy(JObject root)
        {
            var list = new List<CardSpec>();
            foreach (var g in root["gameObjects"])
            {
                var spec = new CardSpec();
                spec.title = (string)g["suggestedName"] ?? "";
                spec.category = (string)g["category"] ?? "";
                spec.description = (string)g["visualMetaphor"] ?? "";
                spec.summary = Shorten(spec.description, 150);
                spec.caption = (string)g["conceptualOrigin"] ?? "";
                spec.primary = ((string)g["behaviourHint"] ?? "").ToLower().Contains("primary");
                spec.color = ParseColor(null, spec.category);

                string displayType = ((string)g["displayType"] ?? "text").ToLower();
                if (displayType == "table")
                {
                    spec.kind = Kind.Table;
                    spec.headers = SplitPipes((string)g["tableHeaders"]);
                    spec.rows = new List<List<string>>();
                    string tr = (string)g["tableRows"];
                    if (!string.IsNullOrEmpty(tr))
                        foreach (var rowStr in tr.Split(';'))
                            spec.rows.Add(SplitPipes(rowStr));
                }
                else if (displayType == "image")
                {
                    spec.kind = Kind.Image;
                    { var ri = (string)g["relatedImage"]; if (!string.IsNullOrEmpty(ri)) spec.imageRefs.Add(ri); }
                }
                else
                {
                    spec.kind = Kind.Text;
                }
                list.Add(spec);
            }
            return list;
        }

        private static List<string> SplitPipes(string s)
        {
            var list = new List<string>();
            if (string.IsNullOrEmpty(s)) return list;
            foreach (var p in s.Split('|')) list.Add(p.Trim());
            return list;
        }

        // ------------------------------------------------------------------ build a card

private void BuildCard(CardSpec spec, Vector3 pos, float rotY, float rotZ, int index)
        {
            GameObject card = Instantiate(cardBasePrefab, pos, Quaternion.Euler(0f, rotY, rotZ));
            card.name = "Card" + (index + 1).ToString("00") + "_" + Sanitize(spec.title);
            _spawned.Add(card);

            // textos
            SetTmp(card.transform, "Canvas/Collapsed/Title", spec.title);
            SetTmp(card.transform, "Canvas/Collapsed/Summary", spec.summary);
            SetTmp(card.transform, "Canvas/Expanded/Title", spec.title);
            SetTmp(card.transform, "Canvas/Expanded/Description", spec.description);
            SetTmp(card.transform, "Canvas/Expanded/Caption", spec.caption);

            // badge (cor + rotulo da categoria) nos dois estados
            ApplyBadge(card.transform, "Canvas/Collapsed/CategoryBadge", spec);
            ApplyBadge(card.transform, "Canvas/Expanded/CategoryBadge", spec);

            // VFX de abertura
            var bridge = card.GetComponent<CardClickVFXBridge>();
            if (bridge != null)
            {
                bridge.vfxManager = vfxManager;
                bridge.effectIndex = openVfxIndex;
                bridge.spawnAtThisCard = true;
            }

            // figura(s) — injeta no Figure_Box; CardContentFitter cuida da orientacao
            var figureRaw = FindRawImage(card.transform, "Canvas/Expanded/Figure_Box/Figure");
            ImageCarousel3D carousel = null;

            if (spec.kind == Kind.Image)
            {
                var texs = LoadFigureTextures(spec);
                Texture2D first = texs.Count > 0 ? texs[0] : null;

                if (first != null && figureRaw != null)
                {
                    figureRaw.texture = first;
                    figureRaw.color = Color.white;
                    figureRaw.enabled = true;
                    var arf = figureRaw.GetComponent<AspectRatioFitter>();
                    if (arf != null && first.height > 0)
                    {
                        arf.aspectMode = AspectRatioFitter.AspectMode.FitInParent;
                        arf.aspectRatio = (float)first.width / first.height;
                    }
                }
                else if (figureRaw != null) figureRaw.enabled = false;

                // Varias figuras germinadas (FIG_N_X) -> um unico card com setas laterais.
                if (texs.Count > 1 && figureRaw != null)
                {
                    carousel = card.GetComponent<ImageCarousel3D>();
                    if (carousel == null) carousel = card.AddComponent<ImageCarousel3D>();
                    carousel.textures = texs;
                    carousel.targetImage = figureRaw;
                    carousel.aspectFitter = figureRaw.GetComponent<AspectRatioFitter>();
                    carousel.tint = spec.color;
                    carousel.Initialize(card.GetComponent<Card3D>(), figureRaw.GetComponent<RectTransform>());
                }
            }
            else if (figureRaw != null)
            {
                // card de texto/tabela nao mostra a caixa de figura
                figureRaw.texture = null;
                figureRaw.enabled = false;
            }

            // tabela interativa (card de tabela)
            if (spec.kind == Kind.Table)
                BuildTableFollower(card, spec);

            // Cards visuais (imagem/tabela): sem texto, so o conteudo visual
            if (spec.kind == Kind.Image || spec.kind == Kind.Table)
            {
                var fitter = card.GetComponent<CardContentFitter>();
                if (fitter != null) fitter.hideText = true;
                SetActiveChild(card.transform, "Canvas/Collapsed/Title", false);
                SetActiveChild(card.transform, "Canvas/Collapsed/Summary", false);
                if (spec.kind == Kind.Image && figureRaw != null && figureRaw.texture != null)
                {
                    var collapsedRaw = InjectCollapsedImage(card.transform, figureRaw.texture);
                    if (carousel != null && collapsedRaw != null)
                    {
                        carousel.collapsedImage = collapsedRaw;
                        carousel.collapsedAspect = collapsedRaw.GetComponent<AspectRatioFitter>();
                    }
                }
            }
        }

private void BuildTableFollower(GameObject card, CardSpec spec)
        {
            int columns = (spec.headers != null && spec.headers.Count > 0) ? spec.headers.Count
                        : (spec.rows != null && spec.rows.Count > 0 ? spec.rows[0].Count : 2);
            int rows = spec.rows != null ? spec.rows.Count : 0;
            if (columns < 1) columns = 1;

            var go = new GameObject("Table_" + Sanitize(spec.title));
            _spawned.Add(go);
            var canvas = go.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.WorldSpace;

            float totalWidth = 40f;
            float totalHeight = totalWidth * (rows + 1) / Mathf.Max(1, columns);
            var rt = go.GetComponent<RectTransform>();
            rt.sizeDelta = new Vector2(totalWidth, totalHeight);

            float scale = tableWorldWidth / totalWidth;
            go.transform.localScale = new Vector3(scale, scale, scale);

            // Tamanho real da tabela no mundo (para o card poder cobri-la).
            float tableWorldHeight = totalHeight * scale;

            var builder = go.AddComponent<TableBuilder>();
            builder.useStaticPaperData = false;     // usa os dados reais do manifest
            builder.totalWidth = totalWidth;
            builder.totalHeight = totalHeight;
            builder.Build(rows, columns, spec.headers, spec.rows);

            var follower = go.AddComponent<CardFollower>();
            follower.target = card.transform;
            // Coloca a tabela SOBRE a face do card (centrada, logo a frente), em vez
            // de flutuar a frente. O card e dimensionado para cobri-la (abaixo).
            follower.localOffset = new Vector3(0f, -0.06f, -0.03f);

            // Faz o card crescer para cobrir a tabela inteira quando expandido.
            var fitter = card.GetComponent<CardContentFitter>();
            if (fitter != null) fitter.SetTableContent(tableWorldWidth, tableWorldHeight);

            go.SetActive(false);

            var toggle = card.GetComponent<CardTableToggle>();
            if (toggle == null) toggle = card.AddComponent<CardTableToggle>();
            toggle.tableObject = go;
        }

        // ------------------------------------------------------------------ helpers

        private void SpawnTitle(string paperTitle)
        {
            if (titlePrefab == null || string.IsNullOrEmpty(paperTitle)) return;

            Vector3 cardsCenter = GetCardsCenter();

            float yOffset = 1.7f; // altura acima dos cards

            Vector3 spawnPos = cardsCenter + new Vector3(-1.2f, yOffset, 0f);

            var t = Instantiate(titlePrefab, spawnPos, Quaternion.identity);
            t.name = "PaperTitle";

            var tmp = t.GetComponent<TMP_Text>() ?? t.GetComponentInChildren<TMP_Text>(true);

            if (tmp != null)
            {
                tmp.text = paperTitle;
                tmp.fontSize = 0.3f;
                tmp.alignment = TextAlignmentOptions.Center;
            }

            _spawned.Add(t);
        }
        private Vector3 GetCardsCenter()
        {
            var cards = new List<Transform>();

            foreach (var go in _spawned)
            {
                if (go == null) continue;

                // só pega cards reais (não tabela nem título)
                if (go.GetComponent<CardContentFitter>() != null)
                    cards.Add(go.transform);
            }

            if (cards.Count == 0)
                return Vector3.zero;

            Vector3 center = Vector3.zero;

            foreach (var c in cards)
                center += c.position;

            center /= cards.Count;

            return center;
        }

        private void ComputeLayout(int i, int total, out Vector3 pos, out float rotY)
        {
            if (i == 0)
            {
                pos = primaryPosition;
                rotY = 0f;
                return;
            }
            int k = i - 1;
            int row = k / perRow;
            int col = k % perRow;
            int remaining = (total - 1) - row * perRow;
            int countInRow = Mathf.Min(perRow, remaining);
            float rowWidth = (countInRow - 1) * xStep;
            float x = -rowWidth * 0.5f + col * xStep;
            float y = primaryPosition.y - (row + 1) * yStep;
            float z = 0.2f + row * 0.05f;
            pos = new Vector3(x, y, z);
            rotY = -x * fanRotationPerX;
        }

        // Leque em Z do deck: primeira carta reta; demais alternam os lados crescendo,
        // para que as cartas empilhadas da mesma tag nao se sobreponham exatamente.
        private float StackRotZ(int j)
        {
            int pair = (j + 1) / 2;
            float sign = (j % 2 == 1) ? 1f : -1f;
            return pair * stackRotZStep * sign;
        }

        private static void SetTmp(Transform root, string path, string value)
        {
            var t = root.Find(path);
            if (t == null) return;
            var tmp = t.GetComponent<TMP_Text>();
            if (tmp != null) tmp.text = value ?? "";
        }

        private static void SetActiveChild(Transform root, string path, bool active)
        {
            var t = root.Find(path);
            if (t != null) t.gameObject.SetActive(active);
        }

private RawImage InjectCollapsedImage(Transform card, Texture tex)
        {
            var collapsed = card.Find("Canvas/Collapsed");
            if (collapsed == null) return null;
            var go = new GameObject("CollapsedFigure",
                typeof(RectTransform), typeof(CanvasRenderer), typeof(RawImage), typeof(AspectRatioFitter));
            go.transform.SetParent(collapsed, false);
            go.transform.SetSiblingIndex(0); // fica atras do badge
            var rt = go.GetComponent<RectTransform>();
            rt.anchorMin = Vector2.zero;
            rt.anchorMax = Vector2.one;
            rt.offsetMin = new Vector2(6f, 6f);
            rt.offsetMax = new Vector2(-6f, -6f);
            var raw = go.GetComponent<RawImage>();
            raw.texture = tex;
            raw.color = Color.white;
            var arf = go.GetComponent<AspectRatioFitter>();
            arf.aspectMode = AspectRatioFitter.AspectMode.FitInParent;
            if (tex.height > 0) arf.aspectRatio = (float)tex.width / tex.height;
            return raw;
        }

// --------------------------------------------------- figuras germinadas

        /// <summary>
        /// Junta unidades de imagem que pertencem a MESMA figura do paper
        /// (mesmo numero N em FIG_N_X) em um unico CardSpec, acumulando as refs.
        /// Ex.: FIG_4_1, FIG_4_2, FIG_4_3 -> 1 card; FIG_5 -> outro card.
        /// </summary>
        private List<CardSpec> MergeGerminatedImages(List<CardSpec> specs)
        {
            var result = new List<CardSpec>();
            var byFigure = new Dictionary<int, CardSpec>();

            foreach (var s in specs)
            {
                if (s.kind != Kind.Image || s.imageRefs == null || s.imageRefs.Count == 0)
                {
                    result.Add(s);
                    continue;
                }

                int n = FigureNumber(s.imageRefs[0]);
                if (n < 0) { result.Add(s); continue; }

                if (byFigure.TryGetValue(n, out var host))
                {
                    foreach (var r in s.imageRefs)
                        if (!host.imageRefs.Contains(r)) host.imageRefs.Add(r);
                }
                else
                {
                    byFigure[n] = s;
                    result.Add(s);
                }
            }

            foreach (var s in result)
                if (s.kind == Kind.Image && s.imageRefs != null && s.imageRefs.Count > 1)
                    s.imageRefs.Sort((a, b) => PartIndex(a).CompareTo(PartIndex(b)));

            return result;
        }

        /// <summary>Carrega, em ordem, todas as texturas de uma figura (parte por parte).</summary>
        private List<Texture2D> LoadFigureTextures(CardSpec spec)
        {
            var texs = new List<Texture2D>();
            if (spec.imageRefs == null) return texs;

            string dir = paperDataFolder.TrimEnd('/') + "/images/";
            var paths = new List<string>();

            // 1) refs declaradas no manifest
            foreach (var r in spec.imageRefs)
            {
                string p = ResolveFigurePath(r, dir);
                if (!string.IsNullOrEmpty(p) && !paths.Contains(p)) paths.Add(p);
            }

            // 2) irmaos germinados existentes no disco (FIG_N_x.png) que o manifest
            //    pode nao ter listado individualmente.
            int n = spec.imageRefs.Count > 0 ? FigureNumber(spec.imageRefs[0]) : -1;
            if (n >= 0)
                foreach (var p in GerminatedSiblings(n, dir))
                    if (!paths.Contains(p)) paths.Add(p);

            paths.Sort((a, b) => PartIndex(a).CompareTo(PartIndex(b)));

            foreach (var p in paths)
            {
                var t = LoadTextureAtPath(p);
                if (t != null) texs.Add(t);
            }

            if (texs.Count == 0)
                Debug.LogWarning("[PaperCaveManifestLoader] Nenhuma figura encontrada para o card '" + spec.title + "'.");
            return texs;
        }

        private string ResolveFigurePath(string imageRef, string dir)
        {
            if (string.IsNullOrEmpty(imageRef)) return null;
            foreach (var name in ImageCandidates(imageRef))
            {
                string p = dir + name;
#if UNITY_EDITOR
                if (AssetDatabase.LoadAssetAtPath<Texture2D>(p) != null) return p;
#endif
                if (System.IO.File.Exists(p)) return p;
            }
            return null;
        }

        private List<string> GerminatedSiblings(int n, string dir)
        {
            var list = new List<string>();
            if (!System.IO.Directory.Exists(dir)) return list;
            var rx = new Regex("^FIG_0*" + n + "_(\\d+)\\.png$", RegexOptions.IgnoreCase);
            foreach (var full in System.IO.Directory.GetFiles(dir, "*.png"))
            {
                string file = System.IO.Path.GetFileName(full);
                if (rx.IsMatch(file)) list.Add(dir + file);
            }
            return list;
        }

        private static Texture2D LoadTextureAtPath(string p)
        {
            if (string.IsNullOrEmpty(p)) return null;
#if UNITY_EDITOR
            var tex = AssetDatabase.LoadAssetAtPath<Texture2D>(p);
            if (tex != null) return tex;
#endif
            if (System.IO.File.Exists(p))
            {
                var bytes = System.IO.File.ReadAllBytes(p);
                var t2 = new Texture2D(2, 2);
                if (t2.LoadImage(bytes)) return t2;
            }
            return null;
        }

        private static int FigureNumber(string s)
        {
            if (string.IsNullOrEmpty(s)) return -1;
            var m = Regex.Match(s, "FIG_?(\\d+)", RegexOptions.IgnoreCase);
            return m.Success ? int.Parse(m.Groups[1].Value) : -1;
        }

        private static int PartIndex(string s)
        {
            if (string.IsNullOrEmpty(s)) return 0;
            var m = Regex.Match(s, "FIG_?\\d+_(\\d+)", RegexOptions.IgnoreCase);
            return m.Success ? int.Parse(m.Groups[1].Value) : 0;
        }


        private static RawImage FindRawImage(Transform root, string path)
        {
            var t = root.Find(path);
            return t != null ? t.GetComponent<RawImage>() : null;
        }

        private void ApplyBadge(Transform root, string path, CardSpec spec)
        {
            var t = root.Find(path);
            if (t == null) return;

            // Cor da badge
            var img = t.GetComponent<Image>();
            if (img != null)
                img.color = spec.color;

            var label = t.Find("Text");
            if (label == null) return;

            var tmp = label.GetComponent<TMP_Text>();
            if (tmp == null) return;

            var badgeRT = t.GetComponent<RectTransform>();

            // Normaliza a categoria
            string category = (spec.category ?? "")
                .Trim()
                .Replace("_", " ");

            // Texto exibido
            if (category.Equals("Graphical Representation", System.StringComparison.OrdinalIgnoreCase))
                tmp.text = "GRAPHICAL REPRESENTATION";
            else
                tmp.text = category.ToUpper();

            // Atualiza o texto antes de medir
            tmp.ForceMeshUpdate();

            // Ajusta automaticamente a largura da badge
            if (badgeRT != null)
            {
                float padding = 20f; // Espaço nas laterais
                float width = tmp.preferredWidth + padding;

                // Largura mínima para categorias pequenas
                width = Mathf.Max(width, 60f);

                badgeRT.sizeDelta = new Vector2(width, badgeRT.sizeDelta.y);
            }

            // Faz o texto ocupar toda a badge
            var textRT = tmp.GetComponent<RectTransform>();
            if (textRT != null)
            {
                textRT.anchorMin = Vector2.zero;
                textRT.anchorMax = Vector2.one;
                textRT.offsetMin = Vector2.zero;
                textRT.offsetMax = Vector2.zero;
            }

            // Centraliza o texto
            tmp.alignment = TextAlignmentOptions.Center;
        }

        private Texture2D LoadFigureTexture(string imageRef)
        {
            if (string.IsNullOrEmpty(imageRef)) return null;
            string dir = paperDataFolder.TrimEnd('/') + "/images/";
            foreach (var name in ImageCandidates(imageRef))
            {
                string p = dir + name;
#if UNITY_EDITOR
                var tex = AssetDatabase.LoadAssetAtPath<Texture2D>(p);
                if (tex != null) return tex;
#endif
                if (System.IO.File.Exists(p))
                {
                    var bytes = System.IO.File.ReadAllBytes(p);
                    var t2 = new Texture2D(2, 2);
                    if (t2.LoadImage(bytes)) return t2;
                }
            }
            Debug.LogWarning("[PaperCaveManifestLoader] Figura não encontrada para ref '" + imageRef + "' em " + dir);
            return null;
        }

        // "FIG1" -> FIG_1.png ; "FIG_2.png" -> FIG_2.png ; "FIG7" -> FIG_7.png
        private IEnumerable<string> ImageCandidates(string raw)
        {
            string s = raw.Trim();
            yield return s;                                   // exato
            if (!s.EndsWith(".png")) yield return s + ".png"; // + extensão

            var m = Regex.Match(s, @"^FIG_?(\d+)(?:_(\d+))?$", RegexOptions.IgnoreCase);
            if (m.Success)
            {
                string main = m.Groups[1].Value;
                if (m.Groups[2].Success)
                    yield return "FIG_" + main + "_" + m.Groups[2].Value + ".png";
                yield return "FIG_" + main + ".png";
                yield return "FIG_" + main + "_1.png";
            }
        }

        private static Color ParseColor(string hex, string category)
        {
            if (!string.IsNullOrEmpty(hex) && ColorUtility.TryParseHtmlString(hex, out var c))
                return c;
            switch ((category ?? "").ToLower())
            {
                case "Contribution": return Hex("#FFB800");
                case "Problem":
                case "Abstract": return Hex("#FF4444");
                case "Method":
                case "graphical_representation": return Hex("#00D4FF");
                case "Metric":
                case "Table": return Hex("#00FF88");
                case "Image": return Hex("#B068FF");
                default: return Hex("#00D4FF");
            }
        }

        private static Color Hex(string h)
        {
            ColorUtility.TryParseHtmlString(h, out var c);
            return c;
        }

        private static string Shorten(string s, int max)
        {
            if (string.IsNullOrEmpty(s)) return "";
            s = s.Trim();
            if (s.Length <= max) return s;
            int cut = s.LastIndexOf(' ', Mathf.Min(max, s.Length - 1));
            if (cut < max * 0.6f) cut = max;
            return s.Substring(0, cut).TrimEnd() + "…";
        }

        private static string Sanitize(string s)
        {
            if (string.IsNullOrEmpty(s)) return "Card";
            return Regex.Replace(s, @"[^A-Za-z0-9]+", "_").Trim('_');
        }
    }
}
