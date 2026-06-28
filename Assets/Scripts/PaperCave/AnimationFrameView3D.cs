using System.Collections;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace PaperCave
{
    /// <summary>
    /// World-space (TextMeshPro) step-through frame viewer for the "animation"
    /// content type. Shows one frame at a time: a bold label, an optional figure
    /// (RawImage when the frame has an assetReference, otherwise a description),
    /// and an "i / N" counter. Previous/Next are driven by physical 3D button
    /// planes (<see cref="Card3DButton"/>). When looping is enabled and the user
    /// has not interacted, frames auto-advance every interval.
    /// </summary>
    public class AnimationFrameView3D : MonoBehaviour, IStepView
    {
        public enum Transition { Fade, Slide }

        [System.Serializable]
        public class Frame
        {
            public string label;
            [TextArea] public string description;
            public Texture image; // optional (assetReference)
        }

        public Frame[] frames;

        public TMP_Text labelText;
        public TMP_Text descriptionText;
        public RawImage imageDisplay;
        public TMP_Text counterText;

        public CanvasGroup contentGroup;   // used for fade
        public RectTransform contentRect;  // used for slide

        public Transition transition = Transition.Slide;
        public bool looping = false;
        public float autoAdvanceInterval = 3f;

        int _index;
        bool _userInteracted;
        float _timer;
        Vector2 _basePos;
        bool _animating;

        void Awake()
        {
            if (contentRect != null) _basePos = contentRect.anchoredPosition;
        }

        void OnEnable()
        {
            _timer = 0f;
            ApplyFrame(_index);
            if (contentGroup != null) contentGroup.alpha = 1f;
            if (contentRect != null) contentRect.anchoredPosition = _basePos;
        }

        void Update()
        {
            if (!looping || _userInteracted || _animating) return;
            if (frames == null || frames.Length < 2) return;

            _timer += Time.deltaTime;
            if (_timer >= autoAdvanceInterval)
            {
                _timer = 0f;
                Step(1, false);
            }
        }

        public void Step(int dir, bool user)
        {
            if (frames == null || frames.Length == 0) return;
            if (user) _userInteracted = true;

            int target = ((_index + dir) % frames.Length + frames.Length) % frames.Length;
            if (target == _index) return;

            if (!gameObject.activeInHierarchy)
            {
                _index = target;
                ApplyFrame(_index);
                return;
            }

            StopAllCoroutines();
            StartCoroutine(transition == Transition.Slide ? SlideTo(target, dir) : FadeTo(target));
        }

        IEnumerator FadeTo(int target)
        {
            _animating = true;
            const float half = 0.1f;
            if (contentGroup != null)
            {
                yield return Lerp(half, t => contentGroup.alpha = Mathf.Lerp(1f, 0f, t));
                _index = target;
                ApplyFrame(_index);
                yield return Lerp(half, t => contentGroup.alpha = Mathf.Lerp(0f, 1f, t));
                contentGroup.alpha = 1f;
            }
            else
            {
                _index = target;
                ApplyFrame(_index);
            }
            _animating = false;
        }

        IEnumerator SlideTo(int target, int dir)
        {
            _animating = true;
            const float half = 0.1f;
            if (contentRect != null)
            {
                float w = contentRect.rect.width;
                if (w <= 1f) w = 120f;
                Vector2 outPos = _basePos + new Vector2(-dir * w, 0f);
                Vector2 inPos = _basePos + new Vector2(dir * w, 0f);

                yield return Lerp(half, t => contentRect.anchoredPosition = Vector2.Lerp(_basePos, outPos, t));
                _index = target;
                ApplyFrame(_index);
                contentRect.anchoredPosition = inPos;
                yield return Lerp(half, t => contentRect.anchoredPosition = Vector2.Lerp(inPos, _basePos, t));
                contentRect.anchoredPosition = _basePos;
            }
            else
            {
                _index = target;
                ApplyFrame(_index);
            }
            _animating = false;
        }

        IEnumerator Lerp(float duration, System.Action<float> apply)
        {
            float t = 0f;
            while (t < duration)
            {
                t += Time.deltaTime;
                apply(Mathf.Clamp01(t / duration));
                yield return null;
            }
            apply(1f);
        }

        void ApplyFrame(int i)
        {
            if (frames == null || frames.Length == 0) return;
            i = Mathf.Clamp(i, 0, frames.Length - 1);
            Frame f = frames[i];

            if (labelText != null) labelText.text = f.label;
            if (counterText != null) counterText.text = (i + 1) + " / " + frames.Length;

            bool hasImage = f.image != null;
            if (imageDisplay != null)
            {
                imageDisplay.gameObject.SetActive(hasImage);
                if (hasImage) imageDisplay.texture = f.image;
            }
            if (descriptionText != null)
            {
                // When a figure exists, show it instead of the description text.
                descriptionText.gameObject.SetActive(!hasImage);
                descriptionText.text = f.description;
            }
        }
    }
}
