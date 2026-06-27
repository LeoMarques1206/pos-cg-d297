using System.Collections.Generic;
using UnityEngine;

public class VFXManager : MonoBehaviour
{
    [System.Serializable]
    public class VFXEntry
    {
        [Header("Prefab")]
        public GameObject prefab;

        [Header("Spawn")]
        public Transform spawnPoint;
        public Vector3 localOffset;

        [Header("Escala")]
        public Vector3 scaleMultiplier = Vector3.one;

        [Header("Configuração")]
        public bool followTarget;
        public float destroyAfter = 5f;
    }

    [SerializeField]
    private List<VFXEntry> effects = new();

    private void Start()
    {
        //PlayEffect(0);
    }

    /// <summary>
    /// CHAMAR ASSIM: PlayEffect(index);
    /// </summary>
    public void PlayEffect(int index)
    {
        if (index < 0 || index >= effects.Count)
        {
            Debug.LogWarning($"VFX index inválido: {index}");
            return;
        }

        VFXEntry effect = effects[index];

        if (effect.prefab == null)
        {
            Debug.LogWarning($"Prefab não configurado no índice {index}");
            return;
        }

        Transform parent = effect.followTarget ? effect.spawnPoint : null;

        Vector3 position =
            effect.spawnPoint != null
                ? effect.spawnPoint.position + effect.localOffset
                : transform.position + effect.localOffset;

        Quaternion rotation =
            effect.spawnPoint != null
                ? effect.spawnPoint.rotation
                : Quaternion.identity;

        GameObject spawned = Instantiate(
            effect.prefab,
            position,
            rotation,
            parent
        );

        // Aplica a escala definida no Inspector
        spawned.transform.localScale = Vector3.Scale(
            spawned.transform.localScale,
            effect.scaleMultiplier
        );

        if (effect.destroyAfter > 0)
            Destroy(spawned, effect.destroyAfter);
    }

    /// <summary>Igual a PlayEffect, mas spawna numa posição de mundo arbitrária (usado por cards dinâmicos).</summary>
    public void PlayEffectAt(int index, Vector3 worldPos)
    {
        if (index < 0 || index >= effects.Count) { Debug.LogWarning($"VFX index inválido: {index}"); return; }
        VFXEntry effect = effects[index];
        if (effect.prefab == null) { Debug.LogWarning($"Prefab não configurado no índice {index}"); return; }
        GameObject spawned = Instantiate(effect.prefab, worldPos + effect.localOffset, Quaternion.identity);
        spawned.transform.localScale = Vector3.Scale(spawned.transform.localScale, effect.scaleMultiplier);
        if (effect.destroyAfter > 0) Destroy(spawned, effect.destroyAfter);
    }
}
