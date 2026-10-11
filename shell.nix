# shell.nix - classic dev shell for nix-shell on NixOS (non-flake).
with import <nixpkgs> {};

let py = (python3).withPackages (p: [ p.pygame p.pyyaml ]);

in mkShell { packages = [ py ]; }
