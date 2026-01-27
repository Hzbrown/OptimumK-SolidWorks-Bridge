import json
import pathlib
import cadquery as cq


    



class carAssembly:
    def __init__(self, path: str):
        self.name = path
        self.front_suspension, self.rear_suspension, self.setup = self.load_jsons(path)



    def load_jsons(self, path: str):
        """Loads front and rear suspension JSON files from the given directory."""
        path = pathlib.Path(path)
        front_json_path = path / "Front_Suspension.json"
        rear_json_path = path / "Rear_Suspension.json"
        setup_json_path = path / "Vehicle_Setup.json"

        with open(front_json_path, 'r') as f:
            front_suspension = json.load(f)
        with open(rear_json_path, 'r') as f:
            rear_suspension = json.load(f)
        with open(setup_json_path, 'r') as f:
            setup = json.load(f)
            
        return front_suspension, rear_suspension, setup
        
    
    def draw_point(
        assy: cq.Assembly,
        name: str,
        xyz,
        size: float = 5.0,
        color=None,
    ):
        """
        Add a fixed point to an assembly as both a marker sphere and a small blue 'sketch point' sphere.

        Coloring rules:
        - If 'CHAS' in name: red
        - If 'UPRI' in name: green
        - If 'ROCK' in name: blue
        - Else: yellow
        """
        x, y, z = xyz
        # Use (x, y, z) as in JSON

        # Determine color by name if not provided
        if color is None:
            if "CHAS" in name:
                color = (1.0, 0.0, 0.0)  # red
            elif "UPRI" in name:
                color = (0.0, 1.0, 0.0)  # green
            elif "ROCK" in name:
                color = (0.0, 0.0, 1.0)  # blue
            else:
                color = (1.0, 1.0, 0.0)  # yellow

        # Sphere marker
        pt = cq.Workplane("XY").sphere(size)
        # Small blue sphere as sketch point
        sketch_point = cq.Workplane("XY").sphere(size * 0.3)

        # Add both to the assembly
        assy.add(
            pt,
            name=name + "_sphere",
            loc=cq.Location(cq.Vector(x, y, z)),
            color=cq.Color(*color),
        )
        assy.add(
            sketch_point,
            name=name + "_sketchpoint",
            loc=cq.Location(cq.Vector(x, y, z)),
            color=cq.Color(0, 0, 1),
        )

    def draw_suspension(suspension: dict, name: str) -> cq.Assembly:
        """
        Draw all points from the JSON schema, rejecting any whose lists contain non-floats.
        """
        assy = cq.Assembly(name=name)


        def is_float_list(val):
            return (
                isinstance(val, list)
                and len(val) == 3
                and all(isinstance(x, (float, int)) for x in val)
            )

        # Traverse all groups and points in the JSON
        for group, points in suspension.items():
            if isinstance(points, dict):
                for pt_name, coords in points.items():
                    if is_float_list(coords):
                        carAssembly.draw_point(
                            assy,
                            f"{group}_{pt_name}",
                            coords,
                            size=3.0,
                        )


        carAssembly.draw_wheels(suspension.get("Wheels", {}), assy)


        return assy
    

    def draw_wheels(wheel: dict, assembly: cq.Assembly) -> cq.Assembly:
        """
        Draws two hollow black cylinders for left and right wheels based on wheel parameters in the JSON schema.
        - Outer diameter: Tire Diameter
        - Inner diameter: Rim Diameter
        - Width: Tire Width
        - Color: Black
        """
        import numpy as np
        for side in ["left", "right"]:
            # Get parameters
            tire_dia = wheel["Tire Diameter"][side]
            rim_dia = wheel["Rim Diameter"][side]
            width = wheel["Tire Width"][side]
            half_track = wheel["Half Track"][side] / 2.0
            lateral_offset = wheel["Lateral Offset"][side]
            longitudinal_offset = wheel["Longitudinal Offset"][side]
            vertical_offset = wheel["Vertical Offset"][side]
            camber = wheel["Static Camber"][side]  # degrees
            toe = wheel["Static Toe"][side]        # degrees

            # Center position (x, y, z):
            y_pos = half_track + lateral_offset if side == "left" else -(half_track + lateral_offset)
            x_pos = longitudinal_offset
            z_pos = vertical_offset

            # Create hollow cylinder (tire) along +x (front), then rotate -90 deg about x to align with +y (left)
            outer = cq.Workplane("XY").circle(tire_dia / 2).circle(rim_dia / 2).extrude(width)
            # Initial rotation: align cylinder axis with +y (left)
            outer = outer.rotate((0, 0, 0), (1, 0, 0), -90)
            # Apply camber (about +x/front), then toe (about +z/up), then translate
            outer = outer.rotate((0, 0, 0), (1, 0, 0), camber)
            outer = outer.rotate((0, 0, 0), (0, 0, 1), toe)
            # Shift up by outer radius and out by half width after all rotations
            # Outward shift is along local +y (left), which is global +y for left, -y for right
            y_shift = width / 2 if side == "left" else -width / 2
            outer = outer.translate((x_pos, y_pos + y_shift, z_pos + tire_dia / 2))

            assembly.add(
                outer,
                name=f"Wheel_{side}",
                color=cq.Color(0, 0, 0),
            )
        return assembly
    
    def draw(self, setup: dict) -> cq.Assembly:
        """Draws the car assembly with front and rear suspensions, offsetting rear by reference distance."""
        front_assy = carAssembly.draw_suspension(self.front_suspension, "Front Suspension")
        rear_assy = carAssembly.draw_suspension(self.rear_suspension, "Rear Suspension")

        # Read reference distance from setup
        ref_dist = setup.get("Reference distance", 0)

        # Combine front and rear assemblies into a main assembly, offsetting rear
        main_assy = cq.Assembly(name="Car Assembly")
        main_assy.add(front_assy, name="Front Suspension")
        main_assy.add(rear_assy, name="Rear Suspension", loc=cq.Location(cq.Vector(-ref_dist, 0, 0)))
        return main_assy


if __name__ == "__main__":
    assembly = carAssembly(r"results/Final EV2024")
    # Draw full car assembly
    car = assembly.draw(assembly.setup)

    # Save as STEP file
    car.save("Car_Assembly.step")
    print("Saved car assembly as Car_Assembly.step")

    # Show in ocp_vscode viewer if available
    try:
        from ocp_vscode import show_object
        show_object(car)
        print("Car assembly shown in ocp_vscode viewer.")
    except ImportError:
        print("ocp_vscode not available. Assembly not shown interactively.")