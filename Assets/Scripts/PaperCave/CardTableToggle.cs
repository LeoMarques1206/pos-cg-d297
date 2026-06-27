using UnityEngine;

namespace PaperCave
{
    [RequireComponent(typeof(Card3D))]
    public class CardTableToggle : MonoBehaviour
    {
        [Tooltip("GameObject a mostrar quando o card estiver expandido.")]
        public GameObject tableObject;

        [Header("Visual expandido")]
        [SerializeField] private Vector3 expandedScale = new Vector3(1.4f, 1.4f, 1f);
        [SerializeField] private Vector3 normalScale = Vector3.one;

        [Tooltip("Offset aplicado quando o card está expandido.")]
        [SerializeField] private Vector3 expandedPositionOffset = new Vector3(0f, 0.15f, -0.2f);

        private Card3D _card;
        private bool _wasExpanded;
        private bool _setupCalled;
        private CardTableHoverSetup _hoverSetup;

        private Vector3 _initialLocalPos;

        void Awake()
        {
            _card = GetComponent<Card3D>();
            _hoverSetup = GetComponent<CardTableHoverSetup>();
        }

        void Start()
        {
            _initialLocalPos = transform.localPosition;

            _wasExpanded = _card.Expanded;
            Sync();
        }

        void Update()
        {
            if (_card.Expanded != _wasExpanded)
            {
                _wasExpanded = _card.Expanded;
                Sync();
            }
        }

        private void Sync()
        {
            if (tableObject == null) return;

            bool expanded = _card.Expanded;

            // ativa/desativa tabela
            tableObject.SetActive(expanded);

            // escala do card
            transform.localScale = expanded ? expandedScale : normalScale;

            // deslocamento visual
            transform.localPosition = expanded
                ? _initialLocalPos + expandedPositionOffset
                : _initialLocalPos;

            // setup de hover só uma vez ao expandir
            if (expanded && !_setupCalled && _hoverSetup != null)
            {
                _hoverSetup.RunSetup();
                _setupCalled = true;
            }
        }
    }
}