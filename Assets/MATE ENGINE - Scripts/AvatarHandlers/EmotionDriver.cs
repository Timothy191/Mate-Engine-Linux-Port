using UnityEngine;

/// <summary>
/// Maps emotion tags emitted by the mate bridge ([emotion:joy], [emotion:angry], ...)
/// onto the avatar's VRM expression blendshapes via UniversalBlendshapes.
/// The tag token itself is stripped from the chat text by ChatOllama before display.
/// </summary>
public class EmotionDriver : MonoBehaviour
{
    [Header("Expression Intensities")]
    [Range(0f, 1f)] public float emotionIntensity = 1f;
    [Range(0f, 1f)] public float thinkingIntensity = 0.3f;
    [Range(0f, 1f)] public float alertBlinkPulse = 1f;

    private UniversalBlendshapes blendshapes;
    private float alertPulseUntil;

    private void Awake()
    {
        FindBlendshapes();
    }

    private void FindBlendshapes()
    {
        if (blendshapes != null) return;
        blendshapes = GetComponent<UniversalBlendshapes>();
        if (blendshapes == null) blendshapes = GetComponentInChildren<UniversalBlendshapes>();
        if (blendshapes == null) blendshapes = Object.FindObjectOfType<UniversalBlendshapes>();
    }

    /// <summary>Apply an emotion tag to the avatar face. Unknown tags are ignored.</summary>
    public void SetEmotion(string tag)
    {
        if (blendshapes == null) FindBlendshapes();
        if (blendshapes == null || string.IsNullOrEmpty(tag)) return;

        switch (tag.ToLowerInvariant())
        {
            case "joy":
            case "happy":
                blendshapes.Joy = emotionIntensity;
                blendshapes.Sorrow = 0f;
                blendshapes.Angry = 0f;
                break;
            case "angry":
                blendshapes.Angry = emotionIntensity;
                blendshapes.Joy = 0f;
                blendshapes.Sorrow = 0f;
                break;
            case "sorrow":
            case "sad":
                blendshapes.Sorrow = emotionIntensity;
                blendshapes.Joy = 0f;
                blendshapes.Angry = 0f;
                break;
            case "fun":
            case "relaxed":
                blendshapes.Fun = emotionIntensity;
                break;
            case "thinking":
                blendshapes.Fun = thinkingIntensity;
                break;
            case "alert":
            case "surprised":
                // Brief wide-eye pulse; UniversalBlendshapes fades it back automatically.
                blendshapes.Blink_L = alertBlinkPulse;
                blendshapes.Blink_R = alertBlinkPulse;
                alertPulseUntil = Time.time + 0.15f;
                break;
        }
    }

    private void Update()
    {
        // Release the alert blink so the driver's auto-fade can take over.
        if (alertPulseUntil > 0f && Time.time >= alertPulseUntil)
        {
            if (blendshapes != null)
            {
                blendshapes.Blink_L = 0f;
                blendshapes.Blink_R = 0f;
            }
            alertPulseUntil = 0f;
        }
    }
}
