using UnityEngine;
using UnityEngine.UI;
using TMPro;

namespace PaperCave
{
    /// <summary>
    /// Redimensiona um card 3D (Face, 4 Borders, Canvas) e reorganiza seu conteúdo
    /// (badge, título, figura, caption, descrição) automaticamente de acordo com o
    /// conteúdo real — sem tamanhos fixos hard-coded por card.
    ///
    /// Funciona para QUALQUER card que siga a convenção de nomes abaixo dentro do
    /// expandedView: CategoryBadge, Title, Figure_Box (com um RawImage+AspectRatioFitter
    /// ou Image dentro), Caption, Description.
    ///
    /// Regras de cálculo (genéricas, não específicas de nenhum card):
    /// - A largura do card cresce quando a imagem é landscape (mais larga que alta),
    ///   para acomodá-la sem espremê-la.
    /// - A altura da faixa de imagem é derivada do aspect ratio real do conteúdo
    ///   (RawImage.texture ou Image.sprite) e da largura disponível.
    /// - A altura de cada bloco de texto é medida via TextMeshProUGUI.GetPreferredValues,
    ///   então o card cresce o suficiente para nunca cortar texto.
    /// - O card final é a SOMA de todos os blocos + respiros — não um valor fixo.
    /// </summary>
    public class CardContentFitter : MonoBehaviour
    {
        public enum Orientation { Unknown, Portrait, Landscape }

        [Header("Nomes dos elementos dentro do expandedView")]
        public string badgeName       = "CategoryBadge";
        public string titleName       = "Title";
        public string figureName      = "Figure_Box";
        public string captionName     = "Caption";
        public string descriptionName = "Description";

        [Header("Dimensionamento")]
        [Tooltip("Largura base do card (portrait) em world units. A largura cresce em landscape.")]
        public float baseWidth = 1.6f;

        [Tooltip("Largura máxima permitida em landscape (world units).")]
        public float maxLandscapeWidth = 2.6f;

        [Tooltip("Fração da largura disponível usada pela imagem (o resto é texto, só no modo landscape lado-a-lado). Não usado no modo faixas.")]
        [Range(0.1f, 0.9f)]
        public float imageWidthFraction = 1f;

        [Tooltip("Fração máxima da altura do card que a imagem pode ocupar.")]
        [Range(0.1f, 0.8f)]
        public float maxImageHeightFraction = 0.5f;

        [Tooltip("Espessura visual da borda (world units), mantida constante.")]
        public float borderThickness = 0.05f;

        [Tooltip("Escala de fonte aplicada no modo landscape (cards mais baixos precisam de texto menor).")]
        [Range(0.5f, 1f)]
        public float landscapeFontScale = 0.85f;

        [Tooltip("Velocidade da transição de tamanho (0 = instantâneo).")]
        public float transitionSpeed = 6f;

        [Tooltip("Margens/respiros entre blocos (world units convertidos para canvas units automaticamente).")]
        public float gap = 5f;
        public float sideMargin = 6f;

        [Tooltip("Quando true, esconde badge/titulo/caption/descricao e deixa so o visual preencher o card.")]
        public bool hideText = false;

        public Orientation CurrentOrientation { get; private set; } = Orientation.Unknown;

        // refs
        private Card3D _card;
        private Transform _face, _bTop, _bBottom, _bLeft, _bRight, _canvasTf;
        private RectTransform _canvasRT;
        private RectTransform _badgeRT, _titleRT, _figureRT, _captionRT, _descRT;
        private TextMeshProUGUI _titleTmp, _captionTmp, _descTmp;
        private RawImage _figureRawImage;
        private Image _figureImage;

        // snapshot do layout original (portrait), capturado uma única vez
        private bool _cached;
        private float _origTitleFont, _origCaptionFont, _origDescFont;
        private Vector2 _origBadgeSize;

        // estado de animação
        private Vector2 _currentSize, _targetSize;
        private bool _initializedSize;

        void Awake()
        {
            _card     = GetComponent<Card3D>();
            _face     = transform.Find("Face");
            _bTop     = transform.Find("Border_Top");
            _bBottom  = transform.Find("Border_Bottom");
            _bLeft    = transform.Find("Border_Left");
            _bRight   = transform.Find("Border_Right");
            _canvasTf = transform.Find("Canvas");
            _canvasRT = _canvasTf != null ? _canvasTf.GetComponent<RectTransform>() : null;
        }

        void Start()
        {
            // Cacheia referências e o layout original com o expandedView temporariamente
            // ativo, garantindo medições corretas mesmo que o card comece fechado.
            bool wasActive = _card.expandedView.activeSelf;
            if (!wasActive) _card.expandedView.SetActive(true);
            Canvas.ForceUpdateCanvases();
            CacheRefs();
            ComputeAndApply(immediate: true);
            if (!wasActive) _card.expandedView.SetActive(false);
        }

        void Update()
        {
            if (!_cached) return;

            // Detecta troca do conteúdo de imagem e recalcula tudo
            Texture currentTex = _figureRawImage != null ? _figureRawImage.texture : null;
            Sprite  currentSpr = _figureImage     != null ? _figureImage.sprite     : null;

            bool changed = (currentTex != _lastTexture) || (currentSpr != _lastSprite);
            if (changed)
            {
                _lastTexture = currentTex;
                _lastSprite  = currentSpr;
                ComputeAndApply(immediate: false);
            }

            // Anima a transição de tamanho
            if (_currentSize != _targetSize)
            {
                _currentSize = transitionSpeed <= 0f
                    ? _targetSize
                    : Vector2.Lerp(_currentSize, _targetSize, Time.deltaTime * transitionSpeed);
                ApplyCardSize(_currentSize);
            }
        }

        private Texture _lastTexture;
        private Sprite  _lastSprite;

        private void CacheRefs()
        {
            var view = _card.expandedView.transform;
            _badgeRT   = Find(view, badgeName);
            _titleRT   = Find(view, titleName);
            _figureRT  = Find(view, figureName);
            _captionRT = Find(view, captionName);
            _descRT    = Find(view, descriptionName);

            _titleTmp   = _titleRT   != null ? _titleRT.GetComponent<TextMeshProUGUI>()   : null;
            _captionTmp = _captionRT != null ? _captionRT.GetComponent<TextMeshProUGUI>() : null;
            _descTmp    = _descRT    != null ? _descRT.GetComponent<TextMeshProUGUI>()    : null;

            if (_figureRT != null)
            {
                _figureRawImage = _figureRT.GetComponentInChildren<RawImage>(true);
                _figureImage    = _figureRT.GetComponentInChildren<Image>(true);
            }

            _origBadgeSize   = _badgeRT != null ? _badgeRT.sizeDelta : new Vector2(60f, 14f);
            _origTitleFont   = _titleTmp   != null ? _titleTmp.fontSize   : 9f;
            _origCaptionFont = _captionTmp != null ? _captionTmp.fontSize : 8f;
            _origDescFont    = _descTmp    != null ? _descTmp.fontSize    : 9f;

            _lastTexture = _figureRawImage != null ? _figureRawImage.texture : null;
            _lastSprite  = _figureImage    != null ? _figureImage.sprite    : null;

            if (hideText)
            {
                if (_titleRT   != null) _titleRT.gameObject.SetActive(false);
                if (_captionRT != null) _captionRT.gameObject.SetActive(false);
                if (_descRT    != null) _descRT.gameObject.SetActive(false);
            }

            _cached = true;
        }

        private RectTransform Find(Transform root, string name)
        {
            var t = root.Find(name);
            return t != null ? t.GetComponent<RectTransform>() : null;
        }

        /// <summary>Aspect ratio (largura/altura) do conteúdo de imagem atual, ou -1 se não houver imagem.</summary>
        private float GetContentAspect()
        {
            if (_figureRawImage != null && _figureRawImage.texture != null)
            {
                var tex = _figureRawImage.texture;
                if (tex.height > 0) return (float)tex.width / tex.height;
            }
            if (_figureImage != null && _figureImage.sprite != null)
            {
                var sp = _figureImage.sprite;
                if (sp.rect.height > 0f) return sp.rect.width / sp.rect.height;
            }
            return -1f;
        }

        /// <summary>Recalcula orientação, tamanho do card e layout interno a partir do conteúdo atual.</summary>
        public void ComputeAndApply(bool immediate)
        {
            float aspect = GetContentAspect();
            bool hasImage = aspect > 0f;

            CurrentOrientation = hasImage && aspect > 1.05f ? Orientation.Landscape
                                : hasImage ? Orientation.Portrait
                                : Orientation.Unknown;

            float cardWidth = baseWidth;
            if (CurrentOrientation == Orientation.Landscape)
                cardWidth = Mathf.Min(maxLandscapeWidth, baseWidth * Mathf.Clamp(aspect, 1f, 2.2f));

            // Converte largura mundial para canvas units (escala fixa do Canvas, ex 0.01)
            float canvasScale = (_canvasTf != null && _canvasTf.localScale.x != 0f) ? _canvasTf.localScale.x : 0.01f;
            float canvasW = cardWidth / canvasScale;

            float fontScale = CurrentOrientation == Orientation.Landscape ? landscapeFontScale : 1f;
            if (_titleTmp   != null) _titleTmp.fontSize   = _origTitleFont   * fontScale;
            if (_captionTmp != null) _captionTmp.fontSize = _origCaptionFont * fontScale;
            if (_descTmp    != null) _descTmp.fontSize    = _origDescFont    * fontScale;

            float textAreaW = canvasW - sideMargin * 2f;

            // Altura da imagem: derivada do aspect ratio real, limitada por maxImageHeightFraction
            float imageAreaH = 0f;
            if (hasImage)
            {
                imageAreaH = textAreaW / aspect;
            }

            float badgeH = _origBadgeSize.y;
            float titleH = (hideText || _titleTmp   == null) ? 0f : Mathf.Max(12f, _titleTmp.GetPreferredValues(textAreaW, 0f).y)   + 2f;
            float capH   = (hideText || _captionTmp == null) ? 0f : Mathf.Max(10f, _captionTmp.GetPreferredValues(textAreaW, 0f).y) + 2f;
            float descH  = (hideText || _descTmp    == null) ? 0f : Mathf.Max(10f, _descTmp.GetPreferredValues(textAreaW, 0f).y)    + 2f;

            // Limita a imagem a uma fração máxima da altura TOTAL estimada do card
            float textBlocksH = badgeH + titleH + capH + descH;
            float gapsH = hideText ? (hasImage ? gap * 3f : gap * 2f) : gap * 4f;
            if (hasImage && !hideText)
            {
                float estimatedTotal = imageAreaH + textBlocksH + gapsH + gap;
                float maxImgH = estimatedTotal * maxImageHeightFraction;
                if (imageAreaH > maxImgH) imageAreaH = maxImgH;
            }

            float canvasH;
            if (hideText)
                canvasH = hasImage ? badgeH + imageAreaH + gapsH : badgeH + gapsH;
            else
                canvasH = (hasImage ? imageAreaH + gap : 0f) + textBlocksH + gapsH;

            float worldHeight = canvasH * canvasScale;

            _targetSize = new Vector2(cardWidth, worldHeight);
            if (!_initializedSize || immediate)
            {
                _currentSize = _targetSize;
                _initializedSize = true;
            }

            ApplyCardSize(_currentSize);
            ApplyInternalLayout(canvasW, canvasH, imageAreaH, badgeH, titleH, capH, descH, hasImage);
        }

        private void ApplyCardSize(Vector2 size)
        {
            float halfW = size.x * 0.5f;
            float halfH = size.y * 0.5f;

            if (_face != null) _face.localScale = new Vector3(size.x, size.y, 1f);

            if (_bTop != null)
            {
                _bTop.localPosition = new Vector3(0f, halfH, _bTop.localPosition.z);
                _bTop.localScale    = new Vector3(size.x + borderThickness, borderThickness, 1f);
            }
            if (_bBottom != null)
            {
                _bBottom.localPosition = new Vector3(0f, -halfH, _bBottom.localPosition.z);
                _bBottom.localScale    = new Vector3(size.x + borderThickness, borderThickness, 1f);
            }
            if (_bLeft != null)
            {
                _bLeft.localPosition = new Vector3(-halfW, 0f, _bLeft.localPosition.z);
                _bLeft.localScale    = new Vector3(borderThickness, size.y + borderThickness, 1f);
            }
            if (_bRight != null)
            {
                _bRight.localPosition = new Vector3(halfW, 0f, _bRight.localPosition.z);
                _bRight.localScale    = new Vector3(borderThickness, size.y + borderThickness, 1f);
            }

            if (_canvasRT != null && _canvasTf != null)
            {
                float sx = _canvasTf.localScale.x != 0f ? _canvasTf.localScale.x : 0.01f;
                float sy = _canvasTf.localScale.y != 0f ? _canvasTf.localScale.y : 0.01f;
                _canvasRT.sizeDelta = new Vector2(size.x / sx, size.y / sy);
            }
        }

        private void ApplyInternalLayout(float canvasW, float canvasH, float imageAreaH,
            float badgeH, float titleH, float capH, float descH, bool hasImage)
        {
            if (hideText)
            {
                float cy = -gap;
                if (_badgeRT != null)
                {
                    _badgeRT.gameObject.SetActive(true);
                    _badgeRT.anchorMin        = new Vector2(0f, 1f);
                    _badgeRT.anchorMax        = new Vector2(0f, 1f);
                    _badgeRT.pivot            = new Vector2(0f, 1f);
                    _badgeRT.anchoredPosition = new Vector2(sideMargin, cy);
                }
                cy -= badgeH + gap;
                if (hasImage && _figureRT != null)
                {
                    _figureRT.gameObject.SetActive(true);
                    _figureRT.anchorMin        = new Vector2(0f, 1f);
                    _figureRT.anchorMax        = new Vector2(1f, 1f);
                    _figureRT.pivot            = new Vector2(0.5f, 1f);
                    _figureRT.anchoredPosition = new Vector2(0f, cy);
                    _figureRT.sizeDelta        = new Vector2(-sideMargin * 2f, imageAreaH);
                }
                else if (_figureRT != null)
                {
                    _figureRT.gameObject.SetActive(false);
                }
                return;
            }

            float cursorY = -gap;

            if (hasImage && _figureRT != null)
            {
                _figureRT.anchorMin        = new Vector2(0f, 1f);
                _figureRT.anchorMax        = new Vector2(1f, 1f);
                _figureRT.pivot            = new Vector2(0.5f, 1f);
                _figureRT.anchoredPosition = new Vector2(0f, cursorY);
                _figureRT.sizeDelta        = new Vector2(-sideMargin * 2f, imageAreaH);
                cursorY -= imageAreaH + gap;
            }
            else if (_figureRT != null)
            {
                _figureRT.gameObject.SetActive(false);
            }

            if (_badgeRT != null)
            {
                _badgeRT.anchorMin        = new Vector2(0f, 1f);
                _badgeRT.anchorMax        = new Vector2(0f, 1f);
                _badgeRT.pivot            = new Vector2(0f, 1f);
                _badgeRT.anchoredPosition = new Vector2(sideMargin, cursorY);
            }
            cursorY -= badgeH + gap;

            if (_titleRT != null)
            {
                _titleRT.anchorMin        = new Vector2(0f, 1f);
                _titleRT.anchorMax        = new Vector2(1f, 1f);
                _titleRT.pivot            = new Vector2(0.5f, 1f);
                _titleRT.anchoredPosition = new Vector2(0f, cursorY);
                _titleRT.sizeDelta        = new Vector2(-sideMargin * 2f, titleH);
            }
            cursorY -= titleH + gap;

            if (_captionRT != null)
            {
                _captionRT.anchorMin        = new Vector2(0f, 1f);
                _captionRT.anchorMax        = new Vector2(1f, 1f);
                _captionRT.pivot            = new Vector2(0.5f, 1f);
                _captionRT.anchoredPosition = new Vector2(0f, cursorY);
                _captionRT.sizeDelta        = new Vector2(-sideMargin * 2f, capH);
            }
            cursorY -= capH + gap;

            if (_descRT != null)
            {
                _descRT.anchorMin        = new Vector2(0f, 1f);
                _descRT.anchorMax        = new Vector2(1f, 1f);
                _descRT.pivot            = new Vector2(0.5f, 1f);
                _descRT.anchoredPosition = new Vector2(0f, cursorY);
                _descRT.sizeDelta        = new Vector2(-sideMargin * 2f, descH);
            }
        }
    }
}
