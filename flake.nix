{
  description = "Cavemen AI simulation";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/24.11";

  outputs = { self, nixpkgs }: let
    system = builtins.currentSystem;
    pkgs = nixpkgs.legacyPackages.${system};
    py = (pkgs.python3).withPackages (p: [ p.pygame p.pyyaml ]);

  in {
    devShells.${system}.default = pkgs.mkShell { packages = [ py ]; };
    apps.${system}.cavemen = {
      type = "app";
      command = "${py}/bin/python3 -m cavemen";
    };
  };
}
