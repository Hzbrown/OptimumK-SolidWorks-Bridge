using System.Runtime.InteropServices;
using SolidWorks.Interop.sldworks;
using sw_drawer;

class IDrawSuspension
{
    static void Main(string[] args)
    {
        SldWorks swApp = (SldWorks)Marshal.GetActiveObject("SldWorks.Application");

        // All coordinates in meters (divide mm by 1000)
        InsertCoordinate.InsertCoordinateSystem(swApp, "FrontLeftUpper",   1000.500, 0.300, 0.200);
        InsertCoordinate.InsertCoordinateSystem(swApp, "FrontLeftLower",   0.500, 0.300, 0.050);
        InsertCoordinate.InsertCoordinateSystem(swApp, "FrontRightUpper",  0.500, -0.300, 0.200);
        InsertCoordinate.InsertCoordinateSystem(swApp, "FrontRightLower",  0.500, -330.300, 0.050);
        InsertCoordinate.InsertCoordinateSystem(swApp, "RearLeftUpper",   -0.500, 0.300, 0.200);
        InsertCoordinate.InsertCoordinateSystem(swApp, "RearLeftLower",   -500, 2000.300, 0.050, 0,50, 60);
    }
}