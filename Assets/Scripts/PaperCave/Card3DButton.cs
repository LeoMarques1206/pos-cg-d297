using UnityEngine;

namespace PaperCave
{
    /// <summary>
    /// A physical 3D button plane (Previous / Next) for the animation card.
    /// Carries a serialized reference to the frame view it drives and the step
    /// direction, so the wiring survives scene save/load.
    /// <see cref="Card3DController"/> invokes it when its collider is clicked.
    /// </summary>
    [RequireComponent(typeof(Collider))]
    public class Card3DButton : MonoBehaviour
    {
        public AnimationFrameView3D target;
        public int direction = 1; // -1 = previous, +1 = next

        [Tooltip("Alvo generico (ex: ImageCarousel3D) usado quando 'target' nao for um AnimationFrameView3D.")]
        public MonoBehaviour stepTarget;

public void Invoke()
        {
            if (target != null) { target.Step(direction, true); return; }
            var sv = stepTarget as IStepView;
            if (sv != null) sv.Step(direction, true);
        }
    }
}
