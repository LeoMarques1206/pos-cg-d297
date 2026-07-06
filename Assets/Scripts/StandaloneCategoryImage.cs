using UnityEngine;
using UnityEngine.UI;

namespace PaperCave
{
    /// <summary>
    /// Exibe uma Texture2D em um RawImage fora do card.
    /// Basta chamar:
    /// StandaloneCategoryImage.Instance?.SetTexture(texture);
    /// </summary>
    public class StandaloneCategoryImage : MonoBehaviour
    {
        public static StandaloneCategoryImage Instance { get; private set; }

        [Header("Imagem que será exibida")]
        [SerializeField] private RawImage image;

        [SerializeField] private AspectRatioFitter aspectFitter;

        private void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }

            Instance = this;

            if (image != null)
                image.enabled = false;
        }

        /// <summary>
        /// Recebe uma textura e a exibe no RawImage.
        /// </summary>
        public void SetTexture(Texture2D texture)
        {
            if (texture == null)
            {
                Debug.LogWarning("[StandaloneCategoryImage] Textura nula.");
                return;
            }

            if (image == null)
            {
                Debug.LogError("[StandaloneCategoryImage] RawImage não atribuída.");
                return;
            }

            image.texture = texture;
            image.color = Color.white;
            image.enabled = true;

            if (aspectFitter != null && texture.height > 0)
            {
                aspectFitter.aspectMode = AspectRatioFitter.AspectMode.FitInParent;
                aspectFitter.aspectRatio = (float)texture.width / texture.height;
            }
        }

        /// <summary>
        /// Limpa a imagem exibida.
        /// </summary>
        public void Clear()
        {
            if (image == null)
                return;

            image.texture = null;
            image.enabled = false;
        }
    }
}