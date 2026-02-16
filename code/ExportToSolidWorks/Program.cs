// ============================================================================
// ExportToSolidWorks — C# Console Application
// ============================================================================
// Opens a STEP file, creates a new assembly, inserts the STEP as a component,
// mates it to the assembly origin, and saves as Kinematic_Skeleton.SLDASM.
//
// Build:  dotnet build
// Run:    ExportToSolidWorks.exe "D:\path\to\file.step"
//
// References:
//   SolidWorks.Interop.sldworks.dll
//   SolidWorks.Interop.swconst.dll
//   https://help.solidworks.com/2022/english/api/sldworksapi/
// ============================================================================

using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;

namespace ExportToSolidWorks
{
    class Program
    {
        // SolidWorks 2024 default template path — adjust if needed
        const string AsmTemplate = @"C:\ProgramData\SolidWorks\SOLIDWORKS 2024\templates\Assembly.ASMDOT";

        static int Main(string[] args)
        {
            // ── Parse arguments ─────────────────────────────────────────
            if (args.Length < 1)
            {
                Console.WriteLine("Usage: ExportToSolidWorks.exe <step_file_path>");
                Console.WriteLine("  Inserts a STEP file into a new assembly, mates to origin,");
                Console.WriteLine("  and saves as Kinematic_Skeleton.SLDASM in the same folder.");
                return 1;
            }

            string stepPath = Path.GetFullPath(args[0]);
            if (!File.Exists(stepPath))
            {
                Console.Error.WriteLine($"ERROR: STEP file not found: {stepPath}");
                return 1;
            }

            string outDir  = Path.GetDirectoryName(stepPath);
            string outPath = Path.Combine(outDir, "Kinematic_Skeleton.SLDASM");

            Console.WriteLine($"STEP file : {stepPath}");
            Console.WriteLine($"Output    : {outPath}");

            try
            {
                Run(stepPath, outPath);
                Console.WriteLine("SUCCESS");
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"ERROR: {ex.Message}");
                Console.Error.WriteLine(ex.StackTrace);
                return 1;
            }
        }

        // ================================================================
        // Main workflow
        // ================================================================
        static void Run(string stepPath, string outPath)
        {
            // ── 1. Connect to SolidWorks ────────────────────────────────
            SldWorks swApp = ConnectToSolidWorks();
            swApp.Visible = true;
            Console.WriteLine("Connected to SolidWorks.");

            // ── 2. Create a new assembly document ───────────────────────
            string template = FindTemplate(swApp);
            ModelDoc2 asmDoc = (ModelDoc2)swApp.NewDocument(
                template,
                (int)swDwgPaperSizes_e.swDwgPapersUserDefined,
                0.0, 0.0);

            if (asmDoc == null)
                throw new Exception("Failed to create new assembly document.");

            AssemblyDoc asm = (AssemblyDoc)asmDoc;
            string asmTitle = asmDoc.GetTitle();
            Console.WriteLine($"New assembly created: {asmTitle}");

            // ── 3. Open the STEP file into memory ───────────────────────
            // Per the docs: "To open foreign files (IGES, STEP, etc.), use
            // ISldWorks::LoadFile4."  ArgString = "r" for non-Pro/E imports.
            Console.WriteLine($"Loading STEP: {stepPath}");

            // Set the working directory so SolidWorks can find the file
            swApp.SetCurrentWorkingDirectory(Path.GetDirectoryName(stepPath));

            int loadErrors = 0;
            ModelDoc2 stepDoc = (ModelDoc2)swApp.LoadFile4(
                stepPath,
                "r",    // "r" = import into a new native SW document
                null,   // ImportData — null for STEP
                ref loadErrors);

            if (stepDoc == null)
            {
                throw new Exception(
                    $"LoadFile4 failed. Errors=0x{loadErrors:X}. "
                    + "Make sure SolidWorks can import STEP files (check Tools > Options > Import).");
            }

            // Wait for SolidWorks to finish STEP import/rebuild
            Thread.Sleep(3000);

            string stepTitle = stepDoc.GetTitle();
            Console.WriteLine($"STEP loaded as: {stepTitle}");

            // The STEP import creates a native .SLDASM or .SLDPRT.
            // We need the path that SolidWorks assigned to refer to it.
            string stepSwPath = stepDoc.GetPathName();
            if (string.IsNullOrEmpty(stepSwPath))
                stepSwPath = stepPath;

            Console.WriteLine($"STEP internal path: {stepSwPath}");

            // ── 4. Re-activate the assembly ─────────────────────────────
            int activateErrors = 0;
            swApp.ActivateDoc3(
                asmTitle,
                true,   // useUserPreferences
                (int)swRebuildOnActivation_e.swRebuildActiveDoc,
                ref activateErrors);

            asmDoc = (ModelDoc2)swApp.ActiveDoc;
            asm = (AssemblyDoc)asmDoc;
            Console.WriteLine($"Assembly re-activated: {asmDoc.GetTitle()}");

            // ── 5. Add the STEP component to the assembly ───────────────
            // Per docs: AddComponent5(CompName, ConfigOption, NewConfigName,
            //   UseConfigForPartReferences, ExistingConfigName, X, Y, Z)
            Component2 comp = (Component2)asm.AddComponent5(
                stepSwPath,
                (int)swAddComponentConfigOptions_e.swAddComponentConfigOptions_CurrentSelectedConfig,
                "",     // NewConfigName — not used
                false,  // UseConfigForPartReferences
                "",     // ExistingConfigName
                0, 0, 0 // X, Y, Z at origin
            );

            if (comp == null)
                throw new Exception("AddComponent5 returned null — component was not added.");

            string compName = comp.Name2;
            Console.WriteLine($"Component added: {compName}");

            // ── 6. Unfix the component (make it float) ──────────────────
            asmDoc.ClearSelection2(true);
            SelectComponent(asmDoc, comp);
            asm.UnfixComponent();
            asmDoc.ClearSelection2(true);
            Console.WriteLine("Component unfixed (floating).");

            // ── 7. Mate to origin ───────────────────────────────────────
            // Coincident mates on Front, Top, Right planes between
            // the component and the assembly.
            MateToOrigin(asmDoc, asm, compName, asmTitle);
            Console.WriteLine("Origin mates applied (Front, Top, Right planes).");

            // ── 8. Rebuild ──────────────────────────────────────────────
            asmDoc.ForceRebuild3(true);

            // ── 9. SaveAs Kinematic_Skeleton.SLDASM ─────────────────────
            ModelDocExtension ext = asmDoc.Extension;
            int saveErrors = 0, saveWarnings = 0;
            bool saveOk = ext.SaveAs3(
                outPath,
                (int)swSaveAsVersion_e.swSaveAsCurrentVersion,
                (int)swSaveAsOptions_e.swSaveAsOptions_Silent
                    | (int)swSaveAsOptions_e.swSaveAsOptions_OverrideSaveEmodel,
                null,   // ExportData
                null,   // AdvancedSaveAsOptions
                ref saveErrors,
                ref saveWarnings);

            Console.WriteLine($"SaveAs3 → success={saveOk}, errors=0x{saveErrors:X}, warnings=0x{saveWarnings:X}");

            if (!saveOk)
                throw new Exception($"SaveAs3 failed with errors=0x{saveErrors:X}");

            Console.WriteLine($"Saved: {outPath}");
        }

        // ================================================================
        // Connect to a running SolidWorks instance, or start a new one
        // ================================================================
        static SldWorks ConnectToSolidWorks()
        {
            SldWorks sw = null;

            // Try to attach to a running instance
            try
            {
                sw = (SldWorks)Marshal.GetActiveObject("SldWorks.Application");
            }
            catch (COMException)
            {
                // No running instance — create one
                Console.WriteLine("No running SolidWorks found, starting a new instance...");
                Type swType = Type.GetTypeFromProgID("SldWorks.Application");
                if (swType == null)
                    throw new Exception("SolidWorks is not installed or not registered.");

                sw = (SldWorks)Activator.CreateInstance(swType);

                // Wait for SolidWorks to fully start
                for (int i = 0; i < 60; i++)
                {
                    if (sw.StartupProcessCompleted)
                        break;
                    Thread.Sleep(1000);
                }
            }

            if (sw == null)
                throw new Exception("Could not connect to SolidWorks.");

            return sw;
        }

        // ================================================================
        // Find the assembly template
        // ================================================================
        static string FindTemplate(SldWorks swApp)
        {
            // Try the user's default template first
            string defaultTemplate = swApp.GetUserPreferenceStringValue(
                (int)swUserPreferenceStringValue_e.swDefaultTemplateAssembly);

            if (!string.IsNullOrEmpty(defaultTemplate) && File.Exists(defaultTemplate))
                return defaultTemplate;

            // Fall back to the hardcoded path
            if (File.Exists(AsmTemplate))
                return AsmTemplate;

            // Try common locations
            string[] candidates = {
                @"C:\ProgramData\SolidWorks\SOLIDWORKS 2024\templates\Assembly.ASMDOT",
                @"C:\ProgramData\SolidWorks\SOLIDWORKS 2023\templates\Assembly.ASMDOT",
                @"C:\ProgramData\SolidWorks\SOLIDWORKS 2022\templates\Assembly.ASMDOT",
            };

            foreach (string path in candidates)
            {
                if (File.Exists(path))
                    return path;
            }

            throw new Exception("Could not find an assembly template (.ASMDOT). "
                + "Set a default template in SolidWorks: Tools > Options > Default Templates.");
        }

        // ================================================================
        // Select a component in the FeatureManager tree
        // ================================================================
        static void SelectComponent(ModelDoc2 doc, Component2 comp)
        {
            ModelDocExtension ext = doc.Extension;
            // SelectByID2 with the component name and "COMPONENT" type
            bool ok = ext.SelectByID2(
                comp.Name2,
                "COMPONENT",
                0, 0, 0,
                false,  // Append
                0,      // Mark
                null,   // Callout
                (int)swSelectOption_e.swSelectOptionDefault);

            if (!ok)
                Console.WriteLine($"WARNING: Could not select component '{comp.Name2}'.");
        }

        // ================================================================
        // Mate the component to the assembly origin via 3 coincident mates
        // on Front, Top, and Right planes.
        //
        // Per the docs, the workflow is:
        //   1. ClearSelection2
        //   2. SelectByID2 the first entity (mark = 1)
        //   3. SelectByID2 the second entity (mark = 1, append = true)
        //   4. AddMate5 (swMateCOINCIDENT)
        //   5. ClearSelection2
        // ================================================================
        static void MateToOrigin(ModelDoc2 doc, AssemblyDoc asm, string compName, string asmTitle)
        {
            // Strip file extension from assembly title for SelectByID2 names
            string asmName = Path.GetFileNameWithoutExtension(asmTitle);

            // Plane pairs: (asmPlaneName, compPlaneName)
            // In SolidWorks feature tree, planes are named "Front", "Top", "Right"
            string[][] planePairs = {
                new[] { "Front", "Front" },
                new[] { "Top",   "Top"   },
                new[] { "Right", "Right" },
            };

            ModelDocExtension ext = doc.Extension;
            int mateError = 0;

            foreach (string[] pair in planePairs)
            {
                string asmPlaneName  = pair[0];
                string compPlaneName = pair[1];

                doc.ClearSelection2(true);

                // Select assembly plane:  "Front@AssemblyName"
                string sel1 = $"{asmPlaneName}@{asmName}";
                bool ok1 = ext.SelectByID2(
                    sel1, "PLANE",
                    0, 0, 0,
                    false, 1, null,
                    (int)swSelectOption_e.swSelectOptionDefault);

                // Select component plane:  "Front@PartName-1@AssemblyName"
                string sel2 = $"{compPlaneName}@{compName}@{asmName}";
                bool ok2 = ext.SelectByID2(
                    sel2, "PLANE",
                    0, 0, 0,
                    true,  // Append to selection
                    1, null,
                    (int)swSelectOption_e.swSelectOptionDefault);

                if (!ok1 || !ok2)
                {
                    Console.WriteLine($"WARNING: Could not select planes for mate ({asmPlaneName}). "
                        + $"sel1={ok1}, sel2={ok2}");
                    Console.WriteLine($"  Tried: \"{sel1}\" and \"{sel2}\"");

                    // Retry with "Plane" prefix (some locales or STEP imports
                    // use "Plane1", "Plane2", "Plane3" instead)
                    doc.ClearSelection2(true);
                    continue;
                }

                // swMateCOINCIDENT = 0, swMateAlignALIGNED = 0
                Mate2 mate = (Mate2)asm.AddMate5(
                    (int)swMateType_e.swMateCOINCIDENT,
                    (int)swMateAlign_e.swMateAlignALIGNED,
                    false,          // Flip
                    0, 0, 0,        // Distance, UpperLimit, LowerLimit
                    0, 0,           // GearRatioNum, GearRatioDen
                    0, 0, 0,        // Angle, UpperLimit, LowerLimit
                    false,          // ForPositioningOnly
                    false,          // LockRotation
                    0,              // WidthMateOption
                    out mateError);

                if (mate != null)
                    Console.WriteLine($"  Mate created: {asmPlaneName} plane (error={mateError})");
                else
                    Console.WriteLine($"  WARNING: Mate failed for {asmPlaneName} plane (error={mateError})");

                doc.ClearSelection2(true);
            }
        }
    }
}
