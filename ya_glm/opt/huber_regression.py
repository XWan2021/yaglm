import numpy as np

from ya_glm.opt.utils import safe_data_mat_coef_dot, safe_data_mat_coef_mat_dot
from ya_glm.opt.base import Func
from ya_glm.opt.utils import safe_vectorize
from ya_glm.opt.linear_regression import get_lin_reg_lip


def huber_eval_1d(x, knot=1):
    x_abs = abs(x)
    if x_abs <= knot:
        return 0.5 * x ** 2
    else:
        return knot * (x_abs - 0.5 * knot)


_vec_huber_eval = safe_vectorize(huber_eval_1d)


def huber_eval(x, knot=1):
    return _vec_huber_eval(x, knot).sum()


def huber_grad_1d(x, knot=1):

    if abs(x) <= knot:
        return x
    else:
        return knot * np.sign(x)


_vec_huber_grad = safe_vectorize(huber_grad_1d)


def huber_grad(x, knot=1):
    return _vec_huber_grad(x, knot)


class HuberRegLoss(Func):
    """
    The huber regression loss function

    f(coef, intercept) = (1 / n_samples) * huber(y - X * coef + intercept; knot)

    huber(z; knot)
    = 0.5 z^2 if abs(z) <= knot
    = knot  * (abs(z) - 0.5 * knot) if abs(z) > knot

    Parameters
    ----------
    X: array-like, shape (n_samples, n_features)
        The X data matrix.

    y: array-like, shape (n_samples, )
        The outcomes.

    knot: float
        The knot point for the huber function.

    fit_intercept: bool
        Whether or not to include the intercept term.

    lip: None, float
        The (optional) precomputed Lipshitz constant of the gradient.
    """
    def __init__(self, X, y,
                 knot=1.35,  # TODO: sklearn's default; where did they get this?
                 fit_intercept=True, lip=None):

        self.fit_intercept = fit_intercept
        self.X = X
        self.y = y
        self.knot = knot

        if lip is None:
            # TODO: I think this is right
            self._grad_lip = get_lin_reg_lip(X=X,
                                             fit_intercept=fit_intercept)
        else:
            self._grad_lip = lip

    def _eval(self, x):
        pred = safe_data_mat_coef_dot(X=self.X, coef=x,
                                      fit_intercept=self.fit_intercept)

        return (1/self.X.shape[0]) * huber_eval(pred - self.y, knot=self.knot)

    def _grad(self, x):
        pred = safe_data_mat_coef_dot(X=self.X, coef=x,
                                      fit_intercept=self.fit_intercept)

        resid = pred - self.y
        g = huber_grad(resid, knot=self.knot)
        coef_grad = (1/self.X.shape[0]) * self.X.T @ g

        if self.fit_intercept:
            intercept_grad = np.mean(g)
            return np.concatenate([[intercept_grad], coef_grad])

        else:
            return coef_grad


class HuberRegMultiRespLoss(Func):
    """
    The huber regression loss function for multiple outputs.

    f(coef, intercept) = (1 / n_samples) * huber(y - X * coef + intercept; knot)

    huber(z; knot)
    = 0.5 z^2 if abs(z) <= knot
    = knot  * (abs(z) - 0.5 * knot) if abs(z) > knot

    Parameters
    ----------
    X: array-like, shape (n_samples, n_features)
        The X data matrix.

    y: array-like, shape (n_samples, )
        The outcomes.

    knot: float
        The knot point for the huber function.

    fit_intercept: bool
        Whether or not to include the intercept term.

    lip: None, float
        The (optional) precomputed Lipshitz constant of the gradient.
    """
    def __init__(self, X, y, knot=1.35, fit_intercept=True, lip=None):

        self.fit_intercept = fit_intercept
        self.X = X
        self.y = y
        self.knot = knot

        if self.fit_intercept:
            self.coef_shape = (X.shape[1] + 1, y.shape[1])
        else:
            self.coef_shape = (X.shape[1], y.shape[1])

        if lip is None:
            self._grad_lip = get_lin_reg_lip(X=X, fit_intercept=fit_intercept)
        else:
            self._grad_lip = lip

    def _eval(self, x):
        pred = safe_data_mat_coef_mat_dot(X=self.X,
                                          coef=x.reshape(self.coef_shape),
                                          fit_intercept=self.fit_intercept)

        # return (0.5 / self.X.shape[0]) * ((pred - self.y) ** 2).sum()
        resid = pred - self.y
        return (1 / self.X.shape[0]) * huber_eval(resid.ravel(), knot=self.knot)

    def _grad(self, x):
        pred = safe_data_mat_coef_mat_dot(X=self.X,
                                          coef=x.reshape(self.coef_shape),
                                          fit_intercept=self.fit_intercept)

        resid = pred - self.y
        g = huber_grad(resid, knot=self.knot)
        coef_grad = (1/self.X.shape[0]) * self.X.T @ g

        if self.fit_intercept:
            intercept_grad = g.mean(axis=0)
            grad = np.vstack([intercept_grad, coef_grad])

        else:
            grad = coef_grad

        return grad
