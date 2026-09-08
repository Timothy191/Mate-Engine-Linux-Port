using System;
using UnityEngine;
using System.Collections.Generic;
using ollama;
using UnityEngine.UI;
using System.Collections;
using System.IO;
using System.Linq;
using System.Collections.Concurrent;
using LLMUnitySamples;

public class ChatOllama : MonoBehaviour
{
    [Header("Containers")]
    public Transform chatContainer;         
    public Transform inputContainer;        

    [Header("Colors & Font")]
    public Color playerColor = new Color32(81, 164, 81, 255);
    public Color aiColor = new Color32(29, 29, 73, 255);
    public Color fontColor = Color.white;
    public Font font;
    public int fontSize = 16;

    [Header("Bubble Layout")]
    public int bubbleWidth = 600;
    public float textPadding = 10f;
    public float bubbleSpacing = 10f;
    public float bottomPadding = 10f;       
    public Sprite sprite;
    public Sprite roundedSprite16;
    public Sprite roundedSprite32;
    public Sprite roundedSprite64;

    [Header("Input Settings")]
    public string inputPlaceholder = "Message me";

    [Header("Streaming Audio")]
    public AudioSource streamAudioSource;

    [Header("Bubble Materials")]
    public Material playerMaterial;         
    public Material aiMaterial;             
    [Header("Text Materials")]
    public Material playerTextMaterial;      
    public Material aiTextMaterial;        
    [Header("Scroll")]
    public ScrollRect scrollRect;           
    public bool autoScrollOnNewMessage = true;     
    public bool respectUserScroll = true;            

    [Header("History")]
    [Min(0)] public int maxMessages = 100;           
    public bool trimOnlyWhenAtBottom = true;       
    public bool enableOffscreenTrim = false;        

    [Header("Font Colors (per side)")]
    public Color playerFontColor = Color.white;
    public Color aiFontColor = Color.white;

    [Header("Rounded Sprite Radius")]
    [Range(0, 64)]
    public int cornerRadius = 16; 
    
    private bool layoutDirty;

    private InputBubble inputBubble;
    private List<Bubble> chatBubbles = new List<Bubble>();
    private bool blockInput = true;
    private BubbleUI playerUI, aiUI;
    private bool warmUpDone = false;
    private int lastBubbleOutsideFOV = -1;

    private Animator avatarAnimator;
    private Animator lastAvatarAnimator;
    private static readonly int isTalkingHash = Animator.StringToHash("isTalking");

    private Text aiBubbleText;
    private MarkdownTextAutoConverter markdowner;
    private EmotionDriver emotionDriver;
    private string pendingEmotionToken = "";

    private ConcurrentQueue<string> tokenQueue = new ConcurrentQueue<string>();
    
    private volatile bool requestFinished = false;

    void Start()
    {
        avatarAnimator = GetComponent<Animator>();
        markdowner = FindFirstObjectByType<MarkdownTextAutoConverter>();

        if (font == null) font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        if (cornerRadius <= 16) sprite = roundedSprite16;
        else if (cornerRadius <= 32) sprite = roundedSprite32;
        else sprite = roundedSprite64;

        playerUI = new BubbleUI
        {
            sprite = sprite,
            font = font,
            fontSize = fontSize,
            fontColor = playerFontColor,
            bubbleColor = playerColor,
            bottomPosition = 0,
            leftPosition = 0,
            textPadding = textPadding,
            bubbleOffset = bubbleSpacing,
            bubbleWidth = bubbleWidth,
            bubbleHeight = -1
        };

        aiUI = new BubbleUI
        {
            sprite = sprite,
            font = font,
            fontSize = fontSize,
            fontColor = aiFontColor,
            bubbleColor = aiColor,
            bottomPosition = 0,
            leftPosition = 1,
            textPadding = textPadding,
            bubbleOffset = bubbleSpacing,
            bubbleWidth = bubbleWidth,
            bubbleHeight = -1
        };

        Transform inputParent = inputContainer != null ? inputContainer : chatContainer;

        inputBubble = new InputBubble(inputParent, playerUI, "InputBubble", "Loading...", 4);
        inputBubble.AddSubmitListener(onInputFieldSubmit);
        inputBubble.AddValueChangedListener(onValueChanged);
        inputBubble.setInteractable(false);

        ShowLoadedMessages();
        FindAvatarSmart();
        Ollama.Launch();
        WarmUpCallback();
        Ollama.AIName = "assistant";
        Ollama.playerName = "user";
    }

    void OnEnable()
    {
        layoutDirty = true;
    }

    void FindAvatarSmart()
    {
        Animator found = null;
        var loader = FindFirstObjectByType<VRMLoader>();
        if (loader != null)
        {
            var current = loader.GetCurrentModel();
            if (current != null) found = current.GetComponentsInChildren<Animator>(true).FirstOrDefault(a => a && a.gameObject.activeInHierarchy);
        }
        if (found == null)
        {
            var modelParent = GameObject.Find("Model");
            if (modelParent != null) found = modelParent.GetComponentsInChildren<Animator>(true).FirstOrDefault(a => a && a.gameObject.activeInHierarchy);
        }
        if (found == null)
        {
            var all = GameObject.FindObjectsByType<Animator>(FindObjectsInactive.Include, FindObjectsSortMode.None);
            found = all.FirstOrDefault(a => a && a.isActiveAndEnabled);
        }
        if (found != avatarAnimator)
        {
            avatarAnimator = found;
            lastAvatarAnimator = avatarAnimator;
        }
    }

    void RefreshAvatarIfChanged()
    {
        if (avatarAnimator == null || lastAvatarAnimator == null || avatarAnimator != lastAvatarAnimator)
        {
            FindAvatarSmart();
        }
    }

    private void MarkLayoutDirty()
    {
        layoutDirty = true;
    }

    void OnDisable()
    {
        if (streamAudioSource != null && streamAudioSource.isPlaying)
        {
            streamAudioSource.Stop();
            streamAudioSource.volume = 1f; 
        }
        if (avatarAnimator != null) avatarAnimator.SetBool(isTalkingHash, false);
    }

    Bubble AddBubble(string message, bool isPlayerMessage)
    {
        Bubble bubble = new Bubble(chatContainer, isPlayerMessage ? playerUI : aiUI, isPlayerMessage ? "PlayerBubble" : "AIBubble", message);
        chatBubbles.Add(bubble);
        bubble.OnResize(MarkLayoutDirty);

        var image = bubble.GetRectTransform().GetComponentInChildren<Image>(true);
        if (image != null)
        {
            image.material = isPlayerMessage ? playerMaterial : aiMaterial;
        }
        var text = bubble.GetRectTransform().GetComponentInChildren<Text>(true);
        if (text != null)
        {
            Material m = isPlayerMessage ? playerTextMaterial : aiTextMaterial;
            if (m != null)
            {
                text.material = m;
            }
        }

        if (autoScrollOnNewMessage && (!respectUserScroll || IsAtBottom()))
        {
            StartCoroutine(ScrollToBottomNextFrame());
        }

        TrimHistoryIfNeeded();

        return bubble;
    }

    void TrimHistoryIfNeeded()
    {
        if (maxMessages <= 0) return;

        if (chatBubbles.Count > maxMessages)
        {
            if (!trimOnlyWhenAtBottom || IsAtBottom())
            {
                int removeCount = chatBubbles.Count - maxMessages;
                for (int i = 0; i < removeCount; i++)
                {
                    chatBubbles[i].Destroy();
                }
                chatBubbles.RemoveRange(0, removeCount);
                UpdateBubblePositions();
            }
        }
    }

    bool IsAtBottom(float tolerance = 0.01f)
    {
        if (scrollRect == null) return true; 
        return scrollRect.verticalNormalizedPosition <= tolerance;
    }

    void ShowLoadedMessages()
    {
        int start = 0;
        int total = Ollama.LoadChatHistory();
        if (maxMessages > 0)
            start = Mathf.Max(0, total - maxMessages);

        for (int i = start; i < total; i++)
        {
            AddBubble(Ollama.ChatHistory[i].content, i % 2 == 0);
        }
        StartCoroutine(ScrollToBottomNextFrame());
    }

    void onInputFieldSubmit(string newText)
    {
        inputBubble.ActivateInputField();
        if (blockInput || newText.Trim() == "" || Input.GetKey(KeyCode.LeftShift) || Input.GetKey(KeyCode.RightShift))
        {
            StartCoroutine(BlockInteraction());
            return;
        }
        blockInput = true;

        string message = inputBubble.GetText().Replace("\v", "\n");

        AddBubble(message, true);
        Bubble aiBubble = AddBubble("...", false);
        aiBubbleText = aiBubble.bubbleObject.gameObject.GetComponent<Text>();

        while (tokenQueue.TryDequeue(out _)) {}
        pendingEmotionToken = "";
        requestFinished = false;
        
        Ollama.OnStreamFinished += () =>
        {
            requestFinished = true;
        };
        
        Ollama.SetSystemPrompt(File.ReadAllText(Path.Combine(Application.persistentDataPath, "ZomeAI_prompt.txt")));
        
        _ = Ollama.ChatStream((token) => { 
            tokenQueue.Enqueue(token);
        }, SaveLoadHandler.Instance.data.ollamaModel, message);
        
        inputBubble.SetText("");
    }

    private IEnumerator FadeOutStreamAudio(float duration = 0.5f)
    {
        float startVolume = streamAudioSource.volume;

        while (streamAudioSource.volume > 0f)
        {
            streamAudioSource.volume -= startVolume * Time.deltaTime / duration;
            yield return null;
        }

        streamAudioSource.Stop();
        streamAudioSource.volume = startVolume; 
    }

    public void WarmUpCallback()
    {
        warmUpDone = true;
        inputBubble.SetPlaceHolderText(inputPlaceholder);
        AllowInput();
    }

    public void AllowInput()
    {
        blockInput = false;
        inputBubble.ReActivateInputField();
    }

    public void CancelRequests()
    {
        throw new NotImplementedException();
    }

    IEnumerator<string> BlockInteraction()
    {
        inputBubble.setInteractable(false);
        yield return null;
        inputBubble.setInteractable(true);
        inputBubble.MoveTextEnd();
    }

    void onValueChanged(string newText)
    {
        if (Input.GetKey(KeyCode.Return))
        {
            if (inputBubble.GetText().Trim() == "")
                inputBubble.SetText("");
        }
    }

    public void UpdateBubblePositions()
    {
        float y = bottomPadding;
        for (int i = chatBubbles.Count - 1; i >= 0; i--)
        {
            Bubble bubble = chatBubbles[i];
            RectTransform childRect = bubble.GetRectTransform();
            childRect.anchoredPosition = new Vector2(childRect.anchoredPosition.x, y);

            if (enableOffscreenTrim)
            {
                float containerHeight = chatContainer.GetComponent<RectTransform>().rect.height;
                if (y > containerHeight && lastBubbleOutsideFOV == -1)
                {
                    lastBubbleOutsideFOV = i;
                }
            }

            y += bubble.GetSize().y + bubbleSpacing;
        }
        var contentRect = chatContainer.GetComponent<RectTransform>();
        contentRect.SetSizeWithCurrentAnchors(RectTransform.Axis.Vertical, y + bottomPadding);
    }

    void Update()
    {
        RefreshAvatarIfChanged();

        if (!inputBubble.inputFocused() && warmUpDone)
        {
            inputBubble.ActivateInputField();
            StartCoroutine(BlockInteraction());
        }

        if (enableOffscreenTrim && lastBubbleOutsideFOV != -1)
        {
            for (int i = 0; i <= lastBubbleOutsideFOV; i++)
            {
                chatBubbles[i].Destroy();
            }
            chatBubbles.RemoveRange(0, lastBubbleOutsideFOV + 1);
            lastBubbleOutsideFOV = -1;
            UpdateBubblePositions();
        }

        if (requestFinished)
        {
            requestFinished = false;
            if (avatarAnimator != null) avatarAnimator.SetBool(isTalkingHash, false);
            if (streamAudioSource != null && streamAudioSource.isPlaying)
                StartCoroutine(FadeOutStreamAudio());
            AllowInput();
            Ollama.SaveChatHistory();
            layoutDirty = true;
        }

        if (aiBubbleText != null && markdowner != null && !tokenQueue.IsEmpty)
        {
            while (tokenQueue.TryDequeue(out string token))
            {
                // Strip emotion tags from display text and drive the avatar's face instead.
                if (ProcessEmotionTokens(token)) continue;

                markdowner.AppendText(aiBubbleText, token);
                layoutDirty = true;

                if (streamAudioSource != null && !streamAudioSource.isPlaying)
                    streamAudioSource.Play();
                if (avatarAnimator != null) avatarAnimator.SetBool(isTalkingHash, true);
            }
        }
    }

    /// <summary>
    /// Detects [emotion:...] tag tokens streamed by the mate bridge.
    /// Returns true when the token was consumed as an emotion tag (not chat text).
    /// Tags may arrive split across chunk boundaries; partial prefixes are held back.
    /// </summary>
    bool ProcessEmotionTokens(string token)
    {
        if (string.IsNullOrEmpty(token)) return false;

        // A lone tag chunk (whole tag in one token).
        var match = System.Text.RegularExpressions.Regex.Match(token, @"^\[emotion:([A-Za-z]+)\]\s*$");
        if (match.Success)
        {
            ApplyEmotion(match.Groups[1].Value);
            return true;
        }

        // Tag embedded at the start of a content chunk: strip and forward the rest.
        match = System.Text.RegularExpressions.Regex.Match(token, @"^\[emotion:([A-Za-z]+)\]\s*");
        if (match.Success)
        {
            ApplyEmotion(match.Groups[1].Value);
            string rest = token.Substring(match.Length);
            if (rest.Length > 0)
            {
                markdowner.AppendText(aiBubbleText, rest);
                layoutDirty = true;
            }
            return true;
        }

        // An unterminated leading "[emotion:..." means the tag is split across
        // chunks; hold it back and merge it with the next token.
        if (token.StartsWith("[emotion:") && !token.Contains("]"))
        {
            pendingEmotionToken += token;
            return true;
        }
        if (!string.IsNullOrEmpty(pendingEmotionToken))
        {
            string merged = pendingEmotionToken + token;
            pendingEmotionToken = "";
            if (ProcessEmotionTokens(merged)) return true;
            // Merged text turned out to be normal chat text after all.
            markdowner.AppendText(aiBubbleText, merged);
            layoutDirty = true;
            return true;
        }

        return false;
    }

    void ApplyEmotion(string tag)
    {
        if (emotionDriver == null)
        {
            emotionDriver = GetComponent<EmotionDriver>();
            if (emotionDriver == null) emotionDriver = GetComponentInChildren<EmotionDriver>();
            if (emotionDriver == null) emotionDriver = FindObjectOfType<EmotionDriver>();
            if (emotionDriver == null) emotionDriver = gameObject.AddComponent<EmotionDriver>();
        }
        if (emotionDriver != null) emotionDriver.SetEmotion(tag);
    }

    public void ExitGame()
    {
        Debug.Log("Exit button clicked");
        Application.Quit();
    }

    IEnumerator ScrollToBottomNextFrame()
    {
        yield return null;
        Canvas.ForceUpdateCanvases();
        if (scrollRect != null)
            scrollRect.verticalNormalizedPosition = 0f; 
    }

    bool onValidateWarning = true;
    void OnValidate()
    {
        if (cornerRadius <= 16) sprite = roundedSprite16;
        else if (cornerRadius <= 32) sprite = roundedSprite32;
        else sprite = roundedSprite64;
    }

    void LateUpdate()
    {
        if (!layoutDirty) return;
        layoutDirty = false;

        Canvas.ForceUpdateCanvases();
        UpdateBubblePositions();
        
        if (autoScrollOnNewMessage && (!respectUserScroll || IsAtBottom()))
        {
            if (scrollRect != null) scrollRect.verticalNormalizedPosition = 0f;
        }
    }
}