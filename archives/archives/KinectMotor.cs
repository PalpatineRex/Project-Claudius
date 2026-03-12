using System; using System.Runtime.InteropServices; using System.Threading;
class KinectMotor {
    [DllImport("Kinect10.dll")] static extern int NuiInitialize(uint f);
    [DllImport("Kinect10.dll")] static extern int NuiCameraElevationSetAngle(int d);
    [DllImport("Kinect10.dll")] static extern int NuiCameraElevationGetAngle(out int d);

    static void Set(int deg) {
        if(deg<-27)deg=-27; if(deg>27)deg=27;
        NuiCameraElevationSetAngle(deg);
    }
    // OUI : rapide x2
    static void Oui() {
        Set(27); Thread.Sleep(600); Set(-27); Thread.Sleep(600);
        Set(27); Thread.Sleep(600); Set(-27); Thread.Sleep(600);
        Set(0);
    }
    // NON : descend x2, remonte au centre
    static void Non() {
        Set(-27); Thread.Sleep(1800); Set(0); Thread.Sleep(1200);
        Set(-27); Thread.Sleep(1800); Set(0);
    }
    static void SlowTilt(int deg) { Set(deg); Thread.Sleep(1800); }
    static void Main(string[] args) {
        NuiInitialize(1);
        string mode = args.Length>0?args[0]:"oui";
        if(mode=="oui"){ Console.WriteLine("OUI"); Console.Out.Flush(); Oui(); }
        else if(mode=="non"){ Console.WriteLine("NON"); Console.Out.Flush(); Non(); }
        else if(mode=="daemon"){
            Console.WriteLine("READY"); Console.Out.Flush();
            string line;
            while((line=Console.ReadLine())!=null){
                line=line.Trim();
                if(line=="oui"){Oui();Console.WriteLine("OK:oui");}
                else if(line=="non"){Non();Console.WriteLine("OK:non");}
                else if(line=="reset"){Set(0);Console.WriteLine("OK:reset");}
                else if(line.StartsWith("angle:")){SlowTilt(int.Parse(line.Substring(6)));Console.WriteLine("OK:angle");}
                else if(line=="quit")break;
                Console.Out.Flush();
            }
        }
        Console.WriteLine("done");
    }
}