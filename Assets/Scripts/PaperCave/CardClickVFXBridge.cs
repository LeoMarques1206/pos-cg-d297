using UnityEngine;

namespace PaperCave
{
    /// <summary>
    /// Coloque este componente em cada Card3D.
    /// Detecta quando o cartão é aberto (Toggle → Expanded = true)
    /// e dispara PlayEffect(effectIndex) no VFXManager.
    /// </summary>
    [RequireComponent(typeof(Card3D))]
    public class CardClickVFXBridge : MonoBehaviour
    {
        [Tooltip("Referência ao VFXManager da cena.")]
        public VFXManager vfxManager;

        [Tooltip("Índice do efeito na lista 'effects' do VFXManager.")]
        public int effectIndex = 0;

        [Tooltip("Se true, o efeito spawna na posição deste card (usado por cards instanciados dinamicamente) em vez do spawnPoint fixo do VFXManager.")]
        public bool spawnAtThisCard = false;

        private Card3D _card;
        private bool _wasExpanded;

        private void Awake()
        {
            _card = GetComponent<Card3D>();
        }

        private void Start()
        {
            _wasExpanded = _card.Expanded;
        }

        private void Update()
        {
            bool isExpanded = _card.Expanded;

            // Dispara só na transição fechado → aberto
            if (isExpanded && !_wasExpanded)
            {
                if (vfxManager != null)
                {
                    if (spawnAtThisCard) vfxManager.PlayEffectAt(effectIndex, transform.position);
                    else vfxManager.PlayEffect(effectIndex);
                }
                else
                    Debug.LogWarning("[CardClickVFXBridge] VFXManager não atribuído em " + gameObject.name);
            }

            _wasExpanded = isExpanded;
        }
    }
}
