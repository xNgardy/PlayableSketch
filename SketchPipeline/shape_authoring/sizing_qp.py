import numpy as np


def solve(A, b, E, f, G, h, iterations=12000, tolerance=1e-05):
    A = np.asarray(A, float)
    b = np.asarray(b, float)
    n = A.shape[1]
    E = np.asarray(E, float).reshape((-1, n))
    f = np.asarray(f, float)
    G = np.asarray(G, float).reshape((-1, n))
    h = np.asarray(h, float)
    H = A.T @ A + np.eye(n) * 1e-09
    inverse = np.linalg.inv(H)
    x = inverse @ A.T @ b
    K = inverse
    if len(E):
        middle = np.linalg.pinv(E @ inverse @ E.T, rcond=1e-11)
        x += inverse @ E.T @ middle @ (f - E @ x)
        if np.max(np.abs(E @ x - f)) > tolerance:
            return (
                None,
                {
                    "reason": "inconsistent_locks",
                    "equality_error_cm": float(np.max(np.abs(E @ x - f))),
                },
            )
        K = inverse - inverse @ E.T @ middle @ E @ inverse
        K = (K + K.T) / 2
    if not len(G):
        return (x, {"iterations": 0})
    directions = K @ G.T
    diagonal = np.einsum("ij,ji->i", G, directions)
    multipliers = np.zeros(len(G))
    for iteration in range(iterations):
        largest = 0.0
        for i in range(len(G)):
            error = h[i] - G[i] @ x
            if diagonal[i] < 1e-10:
                if error > tolerance:
                    return (None, {"reason": "lock_or_geometry_conflict", "constraint_index": i})
                continue
            updated = max(0.0, multipliers[i] + error / diagonal[i])
            delta = updated - multipliers[i]
            x += directions[:, i] * delta
            multipliers[i] = updated
            largest = max(largest, abs(delta))
        violation = float(np.max(h - G @ x))
        if violation <= tolerance and largest < 1e-06:
            active = np.flatnonzero(np.abs(G @ x - h) < tolerance * 10)
            faces = np.vstack([E, G[active]])
            targets = np.r_[f, h[active]]
            if len(faces):
                polished = x + np.linalg.lstsq(faces, targets - faces @ x, rcond=1e-12)[0]
                if np.max(h - G @ polished) <= tolerance and (
                    not len(E) or np.max(np.abs(E @ polished - f)) <= tolerance
                ):
                    x = polished
            if len(E) and np.max(np.abs(E @ x - f)) > tolerance:
                return (None, {"reason": "numerical_equality_residual"})
            return (x, {"iterations": iteration + 1, "maximum_violation_cm": max(0.0, violation)})
    return (
        None,
        {
            "reason": "infeasible_or_iteration_limit",
            "maximum_violation_cm": float(np.max(h - G @ x)),
        },
    )
