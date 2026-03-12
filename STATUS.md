# Kinect Project - STATUS

## Etat : FONCTIONNEL ET VALIDÉ ✅
Date : 10/03/2026
- Idle blink : OK (moteur bouge physiquement, toutes les 4-8s)
- OUI / NON / hello / think : OK testés en simultané avec idle
- Aucun conflit entre les mouvements et l'idle

## Architecture
- `KinectMotor.exe` : binaire x86 C#, contrôle moteur tilt via Kinect10.dll
- `KinectBridge.py` : bridge Python, auto-blink idle 4-8s, subprocess direct
- `KinectBridge.bat` : lanceur Startup Windows (pythonw, hidden)
- Production : `C:\Kinect\` (binaires seulement)
- Workbench : `C:\Users\PC\Downloads\Claude AI Workbench\kinect\` (sources)

## Règles critiques
- NuiInitialize(1) — NE PAS CHANGER ce flag
- Compilation : csc.exe /platform:x86 — toujours guillemets autour des paths
- Pas de daemon stdin/stdout — subprocess direct uniquement (buffering impossible)
- Tuer KinectMotor.exe avant de recompiler (sinon accès refusé)
- Tuer pythonw avant recompilation si KinectBridge tourne

## Mouvements calibrés et validés
| Cmd   | Angles         | Timings                        |
|-------|----------------|--------------------------------|
| oui   | ±20°           | Sleep(250) entre chaque        |
| non   | -27° x2        | Sleep(700) bas, Sleep(200) centre |
| blink | -10°, retour 0 | Sleep(200) bas, Sleep(200) retour |
| hello | +15° x2        | Sleep(350), Sleep(200) centre  |
| think | ±5°            | Sleep(600)                     |
| reset | 0°             | —                              |

## Ce qui NE marche PAS
- Mode daemon (stdin/stdout) : stdout bloqué en mode no-window, blinks reçus mais moteur inerte
- Angles < 10° pour blink : LED rouge mais moteur ne démarre pas (seuil physique)
- CREATE_NO_WINDOW avec pipes : buffering non flushable même avec Console.Out.Flush()

## Prochaine étape
- KinectDaemon.cs : process C# tout-en-un (RGB stream + depth + moteur)
  remplace ColorBasics-WPF pour les snapshots
