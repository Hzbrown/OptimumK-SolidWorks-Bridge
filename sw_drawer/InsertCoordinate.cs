// https://help.solidworks.com/2021/english/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.IFeatureManager~CreateCoordinateSystemUsingNumericalValues.html
using System;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;

namespace sw_drawer
{
    public static class InsertCoordinate
    {
        /// <summary>
        /// Inserts or replaces a coordinate system in the active SolidWorks document.
        /// </summary>
        /// <param name="swApp">Active SolidWorks application</param>
        /// <param name="name">Name of the coordinate system feature</param>
        /// <param name="x">X position in mm</param>
        /// <param name="y">Y position in mm</param>
        /// <param name="z">Z position in mm</param>
        /// <param name="angleX">Optional: rotation around X axis in degrees (default 0)</param>
        /// <param name="angleY">Optional: rotation around Y axis in degrees (default 0)</param>
        /// <param name="angleZ">Optional: rotation around Z axis in degrees (default 0)</param>
        /// <returns>True if successful</returns>
        public static bool InsertCoordinateSystem(
            SldWorks swApp,
            string name,
            double x, double y, double z,
            double angleX = 0, double angleY = 0, double angleZ = 0)
        {
            ModelDoc2 swDoc = (ModelDoc2)swApp.ActiveDoc;
            if (swDoc == null)
            {
                Console.WriteLine("No active document found.");
                return false;
            }

            bool useRotation = (angleX != 0 || angleY != 0 || angleZ != 0);

            // Use SelectByID2 with "COORDSYS" to check if feature exists (from VBA recording)
            bool exists = swDoc.Extension.SelectByID2(
                name, "COORDSYS",
                0, 0, 0,
                false, 0, null,
                (int)swSelectOption_e.swSelectOptionDefault
            );

            if (exists)
            {
                Console.WriteLine($"Coordinate system '{name}' exists, replacing...");
                swDoc.EditDelete();
            }

            swDoc.ClearSelection2(true);

            // Convert mm -> meters, degrees -> radians
            Feature coordFeat = swDoc.FeatureManager
                .CreateCoordinateSystemUsingNumericalValues(
                    true,                   // UseLocation
                    x / 1000,               // DeltaX (meters)
                    y / 1000,               // DeltaY (meters)
                    z / 1000,               // DeltaZ (meters)
                    useRotation,            // UseRotation
                    angleX * Math.PI / 180, // AngleX (radians)
                    angleY * Math.PI / 180, // AngleY (radians)
                    angleZ * Math.PI / 180  // AngleZ (radians)
                ) as Feature;

            if (coordFeat == null)
            {
                Console.WriteLine($"Failed to create coordinate system '{name}'.");
                return false;
            }

            coordFeat.Name = name;
            swDoc.EditRebuild3();

            Console.WriteLine(useRotation
                ? $"Coordinate system '{name}' created at ({x}, {y}, {z}) mm, angles ({angleX}, {angleY}, {angleZ}) deg."
                : $"Coordinate system '{name}' created at ({x}, {y}, {z}) mm.");

            return true;
        }
    }
}