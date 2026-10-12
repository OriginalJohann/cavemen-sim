{
  description = "Cavemen AI simulation";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/24.11";

  # NOTE: Nix 2.x evaluates flake outputs in pure mode, where `builtins.currentSystem`
  # is unavailable and the evaluator does not pass a `system` argument (verified by
  # probe flakes on nix 2.34.8). We therefore target the local platform explicitly;
  # this dev-only flake only needs to work on x86_64-linux hosts.
  outputs = { self, nixpkgs }: let
    pkgs = nixpkgs.legacyPackages.x86_64-linux;
    py = (pkgs.python3).withPackages (p: [ p.pygame p.pyyaml ]);

    # Flake app schema only allows a store path in `program` (no shell string, no args key), so build a tiny
    # executable launcher derivation; trailing CLI args of "nix run" are forwarded to the app.
    launcher = pkgs.stdenv.mkDerivation {
      name = "cavmen-launcher";
      dontUnpack = true;
      installPhase = ''
        mkdir -p "$out/bin"
        cat > "$out/bin/cavemen" <<'EOS'
#!/bin/sh
exec ${py}/bin/python3 -m cavemen "$@"
EOS
        chmod 0755 "$out/bin/cavemen"
      '';
    };

  in {
    # Expose the Python env so "nix shell ." and "nix shell .#cavemen" work out of the box;
    # apps.cavemen keeps working for "nix run .#cavemen".
    packages.x86_64-linux = { cavemen = py; default = py; };
    devShells.x86_64-linux.default = pkgs.mkShell { packages = [ py ]; };
    apps.x86_64-linux.cavemen = {
      type = "app";
      program = "${launcher}/bin/cavemen";
    };
  };
}
