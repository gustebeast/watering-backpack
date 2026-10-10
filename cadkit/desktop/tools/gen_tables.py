"""The two tables the surface model needs, written as WGSL (src/tables.wgsl).

The reference tracer (Cycles' Principled BSDF, "multiscatter GGX") does two things a plain GGX lobe does not:
  * it gives back the light a rough lobe loses to its own shadowing: the lobe is scaled by 1 + Fms (1 - E) / E,
    E(mu, rough) being the lobe's albedo with a mirror's Fresnel (what one bounce keeps);
  * under a dielectric's gloss the diffuse gets what the gloss did not take: 1 - (the gloss lobe's own albedo
    with the REAL Fresnel of glass of index 1.5, not Schlick's curve).
Both albedos are integrals with no closed form: tabulated here over mu = cos(view, normal) and
rough = sqrt(alpha) (the Principled roughness itself), N x N, read bilinearly.
"""
import numpy as np

N = 16
IOR = 1.5


def fresnel(c, eta=IOR):
    g = eta * eta - 1 + c * c
    g = np.sqrt(np.maximum(g, 0))
    A = (g - c) / (g + c)
    B = (c * (g + c) - 1) / (c * (g - c) + 1)
    return 0.5 * A * A * (1 + B * B)


def albedos(mu, rough, n=256):
    a = max(rough * rough, 1e-3)
    mu = max(mu, 1e-3)
    wo = np.array([np.sqrt(1 - mu * mu), 0.0, mu])
    # visible-normal sampling of GGX: weight of a sample is F * G2 / G1
    u1, u2 = np.meshgrid((np.arange(n) + 0.5) / n, (np.arange(n) + 0.5) / n)
    u1, u2 = u1.ravel(), u2.ravel()
    vh = np.array([a * wo[0], a * wo[1], wo[2]])
    vh /= np.linalg.norm(vh)
    t1 = np.array([-vh[1], vh[0], 0.0])
    ln = np.linalg.norm(t1)
    t1 = t1 / ln if ln > 1e-9 else np.array([1.0, 0, 0])
    t2 = np.cross(vh, t1)
    r, phi = np.sqrt(u1), 2 * np.pi * u2
    p1, p2 = r * np.cos(phi), r * np.sin(phi)
    s = 0.5 * (1 + vh[2])
    p2 = (1 - s) * np.sqrt(np.maximum(0, 1 - p1 * p1)) + s * p2
    nh = p1[:, None] * t1 + p2[:, None] * t2 + np.sqrt(np.maximum(0, 1 - p1 * p1 - p2 * p2))[:, None] * vh
    h = np.stack([a * nh[:, 0], a * nh[:, 1], np.maximum(0, nh[:, 2])], 1)
    h /= np.linalg.norm(h, axis=1)[:, None]
    vdh = h @ wo
    wi = 2 * vdh[:, None] * h - wo
    nl = wi[:, 2]
    a2 = a * a
    # height-correlated Smith: G2 / G1(view) = (1 + lambda_v) / (1 + lambda_v + lambda_l)
    lam = lambda x: 0.5 * (np.sqrt(1 + a2 * (1 - x * x) / np.maximum(x * x, 1e-12)) - 1)
    g1l = np.where(nl > 0, (1 + lam(mu)) / (1 + lam(mu) + lam(np.maximum(nl, 1e-6))), 0)
    return float(g1l.mean()), float((g1l * fresnel(np.clip(vdh, 0, 1))).mean())


E = np.zeros((N, N))
Ed = np.zeros((N, N))
for i in range(N):          # rough
    for j in range(N):      # mu
        E[i, j], Ed[i, j] = albedos(j / (N - 1), i / (N - 1))
# the lobe's albedo over all view directions: 2 * integral of E mu dmu
mu = np.linspace(0, 1, N)
Eavg = 2 * np.trapezoid(E * mu, mu, axis=1)
real_fss = (IOR - 1) / (4.08567 + 1.00071 * IOR)


def arr(name, a):
    return f"const {name} = array<f32, {a.size}>(" + ", ".join(f"{x:.5f}" for x in a.ravel()) + ");\n"


out = "// Written by tools/gen_tables.py: do not edit. Index [rough * 15][mu * 15], rough = the Principled roughness.\n"
out += f"const TAB_N = {N};\n"
out += arr("TAB_E", E) + arr("TAB_ED", Ed) + arr("TAB_EAVG", Eavg)
out += f"const DIEL_FSS = {real_fss:.5f};   // the mean Fresnel of glass of index {IOR} over the hemisphere (the reference's fit)\n"
open(__file__.replace("\\", "/").rsplit("/", 2)[0] + "/src/tables.wgsl", "w", encoding="utf-8", newline="\n").write(out)
print("E corners", E[0, 0], E[0, -1], E[-1, 0], E[-1, -1], "Ed at rough .5 mu .7:", Ed[8, 10], "Eavg", Eavg.round(3))
