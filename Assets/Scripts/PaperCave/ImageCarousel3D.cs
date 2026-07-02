using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace PaperCave
{
    /// <summary>
    /// Contrato minimo para botoes fisicos de avancar/voltar (Card3DButton).
    /// Implementado tanto por AnimationFrameView3D quanto por ImageCarousel3D,
    /// para que o mesmo pipeline de input (Card3DController -> Card3DButton)
    /// consiga acionar qualquer um dos dois.
    /// </summary>
    public interface IStepView
    {
        void Step(int dir, bool user);
    }

    /// <summary>
    /// Faz UM unico card de imagem exibir varias figuras germinadas
    /// (FIG_N_1, FIG_N_2, FIG_N_3 ...) ocupando o mesmo espaco, uma de cada vez,
    /// e trocando atraves de setas 3D nas laterais do card.
    ///
    /// Reaproveita a anatomia existente: a textura e injetada no mesmo RawImage do
    /// Figure_Box, entao o <see cref="CardContentFitter"/> detecta a troca e
    /// re-ajusta a geometria do card automaticamente (portrait/landscape) a cada
    /// figura. As setas sao planos 3D com BoxCollider + <see cref="Card3DButton"/>,
    /// detectados pelo mesmo Physics.RaycastAll do <see cref="Card3DController"/>.
    ///
    /// As setas vivem sob o "expandedExtra" do Card3D, entao aparecem apenas no
    /// estado expandido e somem quando o card volta a colapsar.
    /// </summary>
    [DisallowMultipleComponent]
    public class ImageCarousel3D : MonoBehaviour, IStepView
    {
        [Header("Figuras germinadas (em ordem)")]
        public List<Texture2D> textures = new List<Texture2D>();

        [Header("Alvos visuais")]
        [Tooltip("RawImage do Figure_Box no estado expandido.")]
        public RawImage targetImage;
        public AspectRatioFitter aspectFitter;
        [Tooltip("Opcional: figura espelhada no estado colapsado (mantida em sincronia).")]
        public RawImage collapsedImage;
        public AspectRatioFitter collapsedAspect;

        [Header("Setas")]
        public Color tint = new Color(0f, 0.83f, 1f, 1f);
        [Tooltip("Tamanho (world units) das setas com o card em escala 1.")]
        public float arrowSize = 0.16f;
        [Tooltip("Quanto a seta entra para dentro da borda da figura (fracao da meia-largura).")]
        [Range(0f, 0.5f)]
        public float edgeInset = 0.06f;

        private Card3D _card;
        private RectTransform _figureRT;
        private Transform _extraRoot;
        private Transform _prevArrow, _nextArrow;
        private Camera _cam;
        private int _index;

        private static readonly Vector3[] _corners = new Vector3[4];

        public int Count => textures != null ? textures.Count : 0;
        public int CurrentIndex => _index;

        /// <summary>Liga o carrossel a um card ja instanciado e cria as setas.</summary>
        public void Initialize(Card3D card, RectTransform figureRT)
        {
            _card = card;
            _figureRT = figureRT;
            _cam = Camera.main;

            EnsureExtraRoot();
            BuildArrows();

            bool hasMany = Count > 1;
            if (_prevArrow != null) _prevArrow.gameObject.SetActive(hasMany);
            if (_nextArrow != null) _nextArrow.gameObject.SetActive(hasMany);

            _index = 0;
            Apply(_index);
        }

        // --------------------------------------------------------- IStepView

        public void Step(int dir, bool user)
        {
            if (Count == 0) return;
            int target = ((_index + dir) % Count + Count) % Count;
            if (target == _index) return;
            _index = target;
            Apply(_index);
        }

        public void Show(int i) { _index = i; Apply(_index); }

        // ------------------------------------------------------------ visual

        private void Apply(int i)
        {
            if (Count == 0) return;
            i = Mathf.Clamp(i, 0, Count - 1);
            Texture2D tex = textures[i];
            if (tex == null) return;

            ApplyTexture(targetImage, aspectFitter, tex);
            ApplyTexture(collapsedImage, collapsedAspect, tex);
        }

        private static void ApplyTexture(RawImage img, AspectRatioFitter arf, Texture2D tex)
        {
            if (img == null) return;
            img.texture = tex;
            img.color = Color.white;
            img.enabled = true;
            if (arf != null && tex.height > 0)
            {
                arf.aspectMode = AspectRatioFitter.AspectMode.FitInParent;
                arf.aspectRatio = (float)tex.width / tex.height;
            }
        }

        // ------------------------------------------------------------- setas

        private void EnsureExtraRoot()
        {
            if (_card != null && _card.expandedExtra != null)
            {
                _extraRoot = _card.expandedExtra.transform;
                return;
            }

            var go = new GameObject("CarouselArrows3D");
            go.transform.SetParent(transform, false);
            go.transform.localPosition = Vector3.zero;
            _extraRoot = go.transform;

            if (_card != null)
            {
                _card.expandedExtra = go;
                go.SetActive(_card.Expanded);
            }
        }

        private void BuildArrows()
        {
            _prevArrow = CreateArrow("ArrowPrev", -1);
            _nextArrow = CreateArrow("ArrowNext", +1);
        }

        private Transform CreateArrow(string label, int direction)
        {
            var go = new GameObject(label,
                typeof(MeshFilter), typeof(MeshRenderer), typeof(BoxCollider), typeof(Card3DButton));
            go.transform.SetParent(_extraRoot, false);
            go.transform.localScale = Vector3.one * arrowSize;

            go.GetComponent<MeshFilter>().sharedMesh = BuildTriangleMesh(direction);

            var mr = go.GetComponent<MeshRenderer>();
            mr.sharedMaterial = BuildArrowMaterial(tint);
            mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            mr.receiveShadows = false;

            var box = go.GetComponent<BoxCollider>();
            box.center = Vector3.zero;
            box.size = new Vector3(1.3f, 1.5f, 0.25f);
            box.isTrigger = false;

            var btn = go.GetComponent<Card3DButton>();
            btn.target = null;        // nao e um AnimationFrameView3D
            btn.stepTarget = this;    // alvo generico via IStepView
            btn.direction = direction;

            return go.transform;
        }

        private static Mesh BuildTriangleMesh(int direction)
        {
            // direction > 0 => aponta para a direita (proxima); < 0 => esquerda (anterior).
            Vector3[] verts = direction >= 0
                ? new[] { new Vector3(-0.5f, 0.6f, 0f), new Vector3(-0.5f, -0.6f, 0f), new Vector3(0.6f, 0f, 0f) }
                : new[] { new Vector3(0.5f, 0.6f, 0f), new Vector3(0.5f, -0.6f, 0f), new Vector3(-0.6f, 0f, 0f) };

            var mesh = new Mesh { name = "CarouselArrow" };
            mesh.vertices = verts;
            mesh.triangles = new[] { 0, 1, 2 };
            mesh.normals = new[] { Vector3.back, Vector3.back, Vector3.back };
            mesh.RecalculateBounds();
            return mesh;
        }

private static Material BuildArrowMaterial(Color color)
        {
            // Shader "always on top": ZTest Always + fila de overlay, para a seta
            // nunca ser cortada pela figura do card.
            var overlay = Shader.Find("PaperCave/ArrowOverlay");
            if (overlay != null)
            {
                var m = new Material(overlay);
                if (m.HasProperty("_Color")) m.SetColor("_Color", color);
                m.renderQueue = 4000;
                return m;
            }

            // Fallback: URP/Unlit (pode ser ocluido em alguns angulos).
            var sh = Shader.Find("Universal Render Pipeline/Unlit");
            if (sh != null)
            {
                var mat = new Material(sh);
                if (mat.HasProperty("_BaseColor")) mat.SetColor("_BaseColor", color);
                if (mat.HasProperty("_Cull")) mat.SetFloat("_Cull", 0f);
                if (mat.HasProperty("_ZTest")) mat.SetFloat("_ZTest", (float)UnityEngine.Rendering.CompareFunction.Always);
                mat.renderQueue = 4000;
                return mat;
            }

            sh = Shader.Find("Unlit/Color");
            if (sh == null) sh = Shader.Find("Sprites/Default");
            var fallback = new Material(sh);
            if (fallback.HasProperty("_Color")) fallback.SetColor("_Color", color);
            fallback.renderQueue = 4000;
            return fallback;
        }

        // ---------------------------------------------------- posicionamento

        void LateUpdate()
        {
            if (_extraRoot == null || !_extraRoot.gameObject.activeInHierarchy) return;
            if (_figureRT == null) return;
            if (_cam == null)
            {
                _cam = Camera.main;
                if (_cam == null) return;
            }

            _figureRT.GetWorldCorners(_corners); // 0=BL, 1=TL, 2=TR, 3=BR

            // Cantos inferiores do card
            Vector3 bottomLeft = _corners[0];
            Vector3 bottomRight = _corners[3];

            // Direção horizontal do card
            Vector3 across = bottomRight - bottomLeft;
            float width = across.magnitude;
            Vector3 dir = across.sqrMagnitude > 1e-6f ? across.normalized : _cam.transform.right;

            // Direção vertical do card
            Vector3 up = (_corners[1] - _corners[0]).normalized;
            float height = Vector3.Distance(_corners[0], _corners[1]);

            // Ajustes de posição
            float horizontalInset = width * 0.35f;//edgeInset;
            float verticalOffset = height * 0.18f; // Aumenta este valor para descer mais

            Vector3 center = (bottomLeft + bottomRight) * 0.5f;
            Vector3 camPush = (_cam.transform.position - center).normalized * 0.03f;

            if (_prevArrow != null && _prevArrow.gameObject.activeSelf)
            {
                Vector3 p = bottomLeft
                            + dir * horizontalInset
                            - up * verticalOffset
                            + camPush;

                _prevArrow.position = p;
                _prevArrow.rotation = Quaternion.LookRotation(p - _cam.transform.position, Vector3.up);
            }

            if (_nextArrow != null && _nextArrow.gameObject.activeSelf)
            {
                Vector3 p = bottomRight
                            - dir * horizontalInset
                            - up * verticalOffset
                            + camPush;

                _nextArrow.position = p;
                _nextArrow.rotation = Quaternion.LookRotation(p - _cam.transform.position, Vector3.up);
            }
        }
    }
}
