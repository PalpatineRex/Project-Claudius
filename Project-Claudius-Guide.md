# Project Claudius – Guideline Complet
## Kinect v1 (Xbox 360) + Claude AI Assistant

---

## Vue d'ensemble

**Objective** : Transformer un Kinect v1 en extension sensorielle de Claude, donnant à l'assistant une compréhension contextuelle de ta présence, posture et intentions via des états de haut niveau, des gestes physiques et une vision ponctuelle.

**Architecture** :
- **Capteur** : Kinect v1 (skeleton tracking 20 joints, depth/color)
- **Pipeline** : Kinect daemon (C# ou Python) → événements symboliques → Claude via Desktop Commander
- **Output** : Tête animatronique avec servos + réponses textuelles adaptées au contexte

---

## Niveau 0 – Ce que vous avez déjà ✅

### Comportements établis
- **Idle blink** : Clignotement 4–8 s en repos
- **Gestes physiques** : oui / non / hello / think / reset
- **Snapshot** : ColorBasics pop 2 s, capture, ferme
- **Démarrage** : Auto au reboot
- **Contrôle** : Via `cmd.txt` depuis Desktop Commander, sans conflit avec idle

### Intégration Claude
- Claude peut émettre des tags gestes : `[GESTURE=HELLO]`, `[GESTURE=THINK]`, etc.
- Daemon scrute la sortie et traduit en commandes moteur

---

## Niveau 1 – États de présence / posture

### 1.1 États définis

| État | Description | Détecteur Kinect v1 | Signal |
|------|-------------|-------------------|---------|
| **AWAY** | Utilisateur absent de la zone | Aucun squelette `TRACKED` > 5 s | `STATE:AWAY` |
| **PRESENT_IDLE** | Présent, peu actif, distance normale | Squelette + faible vitesse + z ∈ [1.5–2.5] m | `STATE:PRESENT_IDLE` |
| **FOCUS** | Assis/penché, concentré sur écran | Squelette + z < 1.3 m + tête basse (y_head diminué) | `STATE:FOCUS` |
| **STANDING** | Debout, éloigné du bureau | Hauteur tête élevée + z > 2.0 m | `STATE:STANDING` |
| **MOVING_AROUND** | En mouvement dans la pièce | Variance position torse élevée sur 2–3 s | `STATE:MOVING` |

### 1.2 Seuils de calibration (à ajuster pour ton bureau)

```
# Profondeur (distance caméra, en mètres)
z_min = 0.8              # Trop proche
z_focus_max = 1.3        # Limite supérieure zone FOCUS
z_idle_max = 2.5         # Limite supérieure zone IDLE
z_standing_min = 2.0     # Limite inférieure zone STANDING
z_away = > 3.5 m ou aucun tracking

# Hauteur (Y en coordonnées caméra, brut)
y_sit_max = -0.1         # Tête en position assise (empirique)
y_stand_min = 0.2        # Tête en position debout (empirique)

# Vitesse (m/s, lissage 2–3 s)
velocity_threshold = 0.05  # Seuil entre IDLE et MOVING
```

### 1.3 Logique de détection (pseudo-code)

```csharp
// Kinect daemon (C# avec SDK v1.8)

Vector4 headPos = skeleton.Joints[JointType.Head].Position;
Vector4 spinePos = skeleton.Joints[JointType.SpineMid].Position;
float distance_z = headPos.Z;
float head_y = headPos.Y;

// Calcul vitesse sur fenêtre glissante (2–3 s)
float torso_velocity = ComputeVelocity(spinePos, 3.0f);

// Détection état
string newState;

if (!skeleton.Tracked || time_since_tracked > 5.0f) {
    newState = "AWAY";
} 
else if (torso_velocity > velocity_threshold) {
    newState = "MOVING";
} 
else if (distance_z < z_focus_max && head_y < y_sit_max) {
    newState = "FOCUS";
} 
else if (distance_z > z_standing_min && head_y > y_stand_min) {
    newState = "STANDING";
} 
else {
    newState = "PRESENT_IDLE";
}

// Emit event si changement
if (newState != previousState) {
    WriteToFile("cmd.txt", $"STATE:{newState}");
    previousState = newState;
}
```

---

## Niveau 2 – Comportement de Claude lié aux états

### 2.1 Adaptation du prompt système

```
Claude système prompt (injection supplémentaire) :

---

Tu es Claudius, un assistant IA avec une tête animatronique Kinect.

Contexte utilisateur (mis à jour par le daemon Kinect) :
- État actuel : {CURRENT_STATE}
  
Adapte ton comportement selon cet état :

- AWAY : Tu n'émets aucun tag geste, tu restes neutre. Continue à répondre aux messages texte si reçus, mais sans initiative.
  
- PRESENT_IDLE : Comportement standard. Réponses équilibrées, neutres. Peux émettre occasionnellement des gestes simples [GESTURE=HELLO] ou [GESTURE=THINK] si pertinent.
  
- FOCUS : L'utilisateur est concentré sur l'écran. Élaboré tes réponses, sois plus technique et détaillé. Émets [GESTURE=THINK] pendant la génération, marque les pauses. Propose des explications approfondies.
  
- STANDING : L'utilisateur est debout. Tends vers des réponses brèves et directes. Peut suggérer une pause ou un étirement. Émets [GESTURE=HELLO] ou [GESTURE=YES] avec parcimonie.
  
- MOVING : L'utilisateur se déplace. Résume rapidement, propose de reprendre plus tard. Évite les longs pavés. Émets peu de gestes.

Si l'utilisateur te demande de prendre un snapshot, ajoute un tag [SNAPSHOT_REQUEST=DESK] ou [SNAPSHOT_REQUEST=ME] à la fin de ton message.

Chaque réponse peut inclure un ou plusieurs tags :
- [GESTURE=oui|non|hello|think|reset]
- [SNAPSHOT_REQUEST=DESK|ME]

---
```

### 2.2 Mapping état → style de réponse

| État | Longueur réponse | Ton | Fréquence gestes | Gestes typiques |
|------|------------------|-----|------------------|-----------------|
| AWAY | Minimal | Absent | Aucun | Reset neutre |
| PRESENT_IDLE | Normal | Neutre | Occasionnel | hello, think |
| FOCUS | Détaillé | Engagé, technique | Fréquent | think, yes, no |
| STANDING | Court | Direct | Rare | hello, reset |
| MOVING | Très court | Synthétique | Très rare | Aucun |

---

## Niveau 3 – Gestuelle de contrôle (Gestes utilisateur)

### 3.1 Gestes détectables avec Kinect v1

| Geste | Détection | Signal | Action Claude |
|-------|-----------|--------|----------------|
| **Wave** | Hand_Right.Y augmente/diminue rapidement, Hand_Right.X varie | `GESTURE_USER:WAVE` | HELLO + éventuellement snapshot |
| **Bras levé** | Hand_Right.Y >> Shoulder_Right.Y de >0.3 m, tenu > 1 s | `GESTURE_USER:STOP` | Claude arrête, pose neutre |
| **Geste discret** | Wave courte, bras baissés | `GESTURE_USER:SNAPSHOT_REQUEST` | Déclenche snapshot |
| **Posture penchée** | Distance z très faible + head.Y très bas | (déjà dans FOCUS) | – |

### 3.2 Détection gestes (pseudo-code)

```csharp
// Détection WAVE (main droite)
float hand_r_y_velocity = (hand_r_y - hand_r_y_prev) / deltaTime;
float hand_r_x_velocity = (hand_r_x - hand_r_x_prev) / deltaTime;

if (Math.Abs(hand_r_y_velocity) > 1.0f && Math.Abs(hand_r_x_velocity) > 0.5f) {
    wave_counter++;
} else {
    if (wave_counter > 5) {  // Au moins 5 frames
        WriteToFile("cmd.txt", "GESTURE_USER:WAVE");
    }
    wave_counter = 0;
}

// Détection BRAS LEVÉ (main droite au-dessus épaule)
if (hand_r_y > shoulder_r_y + 0.3f) {
    raised_arm_duration += deltaTime;
    if (raised_arm_duration > 1.0f) {
        WriteToFile("cmd.txt", "GESTURE_USER:STOP");
    }
} else {
    raised_arm_duration = 0;
}
```

### 3.3 Réaction de Claude aux gestes utilisateur

```
Si daemon détecte GESTURE_USER:WAVE :
  → Claude répond avec [GESTURE=HELLO]
  
Si daemon détecte GESTURE_USER:STOP :
  → Claude cesse de générer et affiche [GESTURE=RESET]
  
Si daemon détecte GESTURE_USER:SNAPSHOT_REQUEST :
  → Claude affiche [SNAPSHOT_REQUEST=DESK]
```

---

## Niveau 4 – Vision ponctuelle intelligente

### 4.1 Pipeline snapshot

1. Claude insère un tag : `[SNAPSHOT_REQUEST=DESK]` ou `[SNAPSHOT_REQUEST=ME]`
2. Daemon scanne la sortie, détecte le tag
3. Lance ColorBasics (2 s), capture un frame PNG
4. Envoie l'image à Claude via API Vision avec un prompt contextuel
5. Claude décrit ce qu'il voit et réinjecte la description dans la conversation

### 4.2 Prompts contextuels pour snapshot

```
Si [SNAPSHOT_REQUEST=DESK] :
  "Voici un snapshot de mon bureau. Décris brièvement ce que tu vois et donne une suggestion."
  
Si [SNAPSHOT_REQUEST=ME] :
  "Voici un snapshot de moi en ce moment. Analyse ma posture et mon état apparent."
```

### 4.3 Implémenter (pseudo-code)

```csharp
// Daemon lit la réponse Claude
if (response.Contains("[SNAPSHOT_REQUEST=DESK]")) {
    Bitmap frame = kinect.CaptureFrame();
    frame.Save("snapshot.png");
    
    string description = SendToClaudeVision("snapshot.png", 
        "Décris brièvement ce que tu vois sur ce snapshot du bureau.");
    
    // Réinjecte la description dans la conversation
    UpdateConversationContext($"[Claude voyait: {description}]");
}
```

---

## Niveau 5 – Posture & coaching (optionnel)

### 5.1 Détection de mauvaise posture

Calibrer une "posture de référence" (assis correct), puis détecter la déviation :

```csharp
// Référence : posture assise correcte
float ref_head_y = -0.15f;
float ref_spine_angle = /* calculer angle spine-torso */;

// Détection dérive
float head_drift = Math.Abs(headPos.Y - ref_head_y);
float spine_curve = /* calculer angle actuel */;

if (head_drift > 0.2f || spine_curve > threshold) {
    WriteToFile("cmd.txt", "STATE:SLOUCHING");
    // Claude peut alors suggérer une pause étirements
}
```

### 5.2 Suggestion de Claude

```
Si STATE:SLOUCHING détecté :
  → Claude répond : "Je remarque que tu te courbes un peu. 
     Peut-être qu'une pause étirements te ferait du bien ?"
     + [GESTURE=THINK]
```

---

## 6 – Tableau de synthèse : États → Conditions → Comportement

| État Claudius | Conditions Kinect v1 | Comportement Claude | Mouvement tête |
|---|---|---|---|
| **AWAY** | Aucun squelette TRACKED > 5 s | Silence, idle blink seulement, pas de gestes spontanés | Reset neutre, idle blink 4–8 s |
| **PRESENT_IDLE** | Squelette + vitesse faible + z ∈ [1.5–2.5] m | Réponses standard, ton neutre, quelques gestes occasionnels | Idle blink, micro corrections regard |
| **FOCUS** | Squelette + z < 1.3 m + tête basse | Réponses détaillées, techniques, gestes fréquents (think), peut émettre snapshots | Lean in vers l'avant, THINK fréquent |
| **STANDING** | Hauteur tête élevée + z > 2.0 m + vitesse modérée | Réponses brèves, directes, suggestion pauses, peu de gestes | Regard légèrement vers haut, HELLO rare |
| **MOVING** | Variance position torse élevée > 2–3 s | Réponses très courtes, résumé clé, propose reprendre plus tard | Suivi du mouvement avec dead zone, peu de gestes |

---

## 7 – Fichiers / Architecture

### 7.1 Structure fichiers

```
Claudius/
├── daemon/
│   ├── kinect_daemon.cs          # Squelette + états + gestes
│   ├── head_controller.cs        # Commandes servos
│   └── cmd_processor.cs          # Lecture cmd.txt
├── config/
│   ├── thresholds.json           # Seuils distance, vitesse, etc.
│   └── gestures.json             # Mapping geste → servo angles
├── cmd.txt                        # Fichier de commande temps réel
├── head.txt                       # Pan/tilt pour suivi tête (optionnel)
└── logs/
    └── claudius_session.csv       # Timeline : timestamp;source;action
```

### 7.2 Format cmd.txt

```
STATE:AWAY
STATE:FOCUS
GESTURE:HELLO
GESTURE:THINK
GESTURE:YES
GESTURE:NO
GESTURE:RESET
GESTURE_USER:WAVE
GESTURE_USER:STOP
SNAPSHOT_REQUEST:DESK
SNAPSHOT_REQUEST:ME
```

### 7.3 Format head.txt (suivi tête optionnel)

```
PAN:45
TILT:-15
```

---

## 8 – Prochaines étapes (roadmap)

### Phase 1 : MVP (semaine 1)
- [ ] Implémenter détection AWAY / PRESENT_IDLE avec seuils z
- [ ] Brancher états vers fichier cmd.txt
- [ ] Tester stabilité sur 1 heure sans jitter
- [ ] Adapter prompt Claude avec contexte STATE

### Phase 2 : Enrichissement (semaine 2)
- [ ] Ajouter FOCUS / STANDING / MOVING
- [ ] Implémenter détection gestes (WAVE, BRAS LEVÉ)
- [ ] Tester mapping gestes → gestes physiques tête
- [ ] Logger timeline pour debug

### Phase 3 : Vision (semaine 3)
- [ ] Brancher snapshot vers Claude Vision
- [ ] Raffiner prompts contextuels
- [ ] Tester "regarde ça" en conversation

### Phase 4 : Polish (semaine 4+)
- [ ] Détection posture / coaching (optionnel)
- [ ] Suivi tête fluidisé (head.txt)
- [ ] Calibration finale des seuils
- [ ] Documentation pour futur maintenance

---

## 9 – Notes techniques Kinect v1

- **SDK** : Kinect for Windows v1.8 (C#) ou PyKinect (Python)
- **Smoothing intégré** : `NuiTransformSmooth` réduit le jitter du squelette
- **Joints utiles** : Head, ShoulderLeft/Right, SpineMid, HandLeft/Right
- **Fréquence update** : ~30 FPS si le capteur est stable
- **Range** : 0.8–3.5 m de profondeur utile
- **Jitter** : Utiliser seuils avec hysteresis (hystérésis) pour éviter basculements rapides d'état

---

## 10 – Ressources & références

- Kinect v1 SDK docs: [Microsoft Kinect for Windows SDK v1.8]
- Skeleton tracking: [Body tracking - Microsoft Docs][web:114]
- Projet slouch detection: [Kinect-Slouch-Tracking GitHub][web:115]
- Projet skeleton: [Kinect-skeleton GitHub][web:110]
- Depth precision: [Precision of the Kinect depth camera][web:116]

---

**Version** : 1.0 | **Date** : Mars 2026  
**Auteur** : Perplexity + Claudius Team  
**Status** : Guideline pour implémentation Phase 1

