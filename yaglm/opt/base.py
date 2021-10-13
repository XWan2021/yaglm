import numpy as np

from scipy.optimize import check_grad, minimize
from warnings import warn


class Func(object):

    # TODO: do we want to do all this numpy conversion automatically?
    def eval(self, x):
        return self._eval(np.array(x, copy=False))

    def grad(self, x):
        return self._grad(np.array(x, copy=False))

    def prox(self, x, step=1):
        """
        The proximal operator defined as

        prox(x, step) = argmin_z step * func(z) + 0.5 * ||x - z||_2^2
        """
        return self._prox(np.array(x), step)

    def conj_prox(self, x, step=1):
        """
        The proximal operator of the conjugate function

        conj_prox(x, step) = argmin_z step * conj_func(z) + 0.5 * ||x - z||_2^2

        where
        conj_func(x) := sup_z <x, z> - func(z)

        We can compute this easily with with just prox using Moreau’s identity

        prox_{s f^*}(y) = y - s prox_{f/s}(y/s)
        """
        return np.array(x, copy=False) - step * self.prox(x=x / step,
                                                          step=1/step)

    def _eval(self, x):
        raise NotImplementedError

    def _grad(self, x):
        raise NotImplementedError

    def _prox(self, x, step):
        raise NotImplementedError

    @property
    def grad_lip(self):
        if hasattr(self, '_grad_lip'):
            return self._grad_lip
        else:
            return None

    @property
    def is_smooth(self):
        """
        Output
        ------
        Whether or not the function is smooth.
        """
        raise NotImplementedError

    @property
    def is_proximable(self):
        """
        Output
        ------
        Whether or not the function has an easy to evaulate proximal operator.
        """
        raise NotImplementedError

    # def eval_and_grad(self, x):
    #     return self.eval(x), self.grad(x)

    # def capabilities(self, x):
    #     # TODO: do we actually need this???

    #     cap = ['EVAL', 'GRAD', 'PROX', 'GRAD_LIP']
    #     try:
    #         self.eval(x)
    #     except NotImplementedError:
    #         cap.remove('EVAL')

    #     try:
    #         self.grad(x)
    #     except NotImplementedError:
    #         cap.remove('GRAD')

    #     try:
    #         self.prox(x, 1)
    #     except NotImplementedError:
    #         cap.remove('PROX')

    #     if self.grad_lip is None:
    #         cap.remove('GRAD_LIP')

    #     return cap


class EntrywiseFunc(Func):
    """
    Represents a function applied entrywise to the input whether the input is a float, vector or array
    """
    def eval(self, x):
        x = np.array(x, copy=False)
        return self._eval(x.reshape(-1))

    def grad(self, x):
        x = np.array(x, copy=False)
        g = self._grad(x.reshape(-1))
        return g.reshape(x.shape)

    def prox(self, x, step=1):
        x = np.array(x, copy=False)
        p = self._prox(x.reshape(-1), step=step)
        return p.reshape(x.shape)


class Zero(Func):
    def _eval(self, x):
        return 0

    def _grad(self, x):
        return np.zeros_like(x)

    def _prox(self, x, step=1):
        return x

    @property
    def is_smooth(self):
        return True

    @property
    def is_proximable(self):
        return True

    @property
    def grad_lip(self):
        return 0


class Sum(Func):
    """
    Represents the sum of an arbitray number of functions.
    """
    def __init__(self, funcs):
        self.funcs = funcs

    def eval(self, x):
        return sum(f.eval(x) for f in self.funcs)

    def grad(self, x):
        return sum(f.grad(x) for f in self.funcs)

    @property
    def grad_lip(self):
        lip = 0
        for f in self.funcs:
            flip = f.grad_lip

            if flip is None:
                return None
            else:
                lip += flip

        return lip

    @property
    def is_smooth(self):
        return all(f.is_smooth for f in self.funcs)

    @property
    def is_proximable(self):
        # False by default, but can be true in special cases
        return False


def check_grad_impl(func, values, atol=1e-05, behavior='ret', verbosity=0):
    """
    Checks the gradient implementation of a function.

    Parameters
    ----------
    func: wlam.opt.Func
        A function implementing fucn.eval and func.grad

    values: list
        The values at which to check the gradient.

    behavior: str
        Must be one of ['ret', 'error', 'warn'].

    atol: float

    """
    assert behavior in ['ret', 'error', 'warn']

    errors = []
    passes = []
    for i, x0 in enumerate(values):

        err = check_grad(func=func.eval, grad=func.grad, x0=x0)
        did_pass = np.allclose(0, err, rtol=0, atol=atol)

        errors.append(err)
        passes.append(did_pass)

        if verbosity >= 1:
            print('value ({}/{}) pass = {}, err = {:1.6f}'.
                  format(i + 1, len(values), did_pass, err))
            print()

        if behavior == 'error':
            assert did_pass

    passes = np.array(passes)

    n_fails = sum(~passes)
    msg = '{}/{} gradients failed: {}'.format(n_fails, len(passes), passes)
    if behavior == 'ret':
        return errors, passes

    if n_fails > 0:
        if behavior == 'warn':
            warn(msg)


def numeric_prox(func, x, step, init=None, force_no_grad=False, **kws):
    """
    Computes the prox operator numerically.

    Parameters
    ----------
    func: func: wlam.opt.Func
        A function implementing fucn.eval and optionally func.grad

    x: array-like

    step: float

    init: array-like
        (Optional) Initialization for the prox numeric solver.

    force_no_grad: bool
        Whether or not to force the algorithm to not use func.grad even if it has one. E.g. some non-smooth functions may have .grad that returns a subgradient which we may not want to use for numeric computaion

    kws: keyword arguments to scipy.optimize.minimize

    Output
    ------
    prox_val: array-like

    opt_out:
    """
    if init is None:
        init = x

    # TODO: some non-differentiable functions may implement
    def get_prox_funcs(x, step):

        def prox_eval(z):
            return step * func.eval(z) + 0.5 * ((z - x) ** 2).sum()

        if not force_no_grad and 'GRAD' in func.capabilities(x):
            def prox_grad(z):
                return step * func.grad(z) + (z - x)
        else:
            prox_grad = None

        return prox_eval, prox_grad

    prox_eval, prox_grad = get_prox_funcs(x=x, step=step)
    opt_out = minimize(fun=prox_eval, x0=init, jac=prox_grad, **kws)

    return opt_out.x, opt_out


def check_prox_impl(func, values, step=0.5,
                    rtol=1e-5, atol=1e-5, behavior='ret',
                    verbosity=0, opt_kws={}):
    """
    Checks the prox implementation of a function.

    Parameters
    ----------
    func: wlam.opt.Func
        A function implementing fucn.eval and func.grad

    values: list
        The values at which to check the gradient.

    behavior: str
        Must be one of ['ret', 'error', 'warn'].

    atol: float

    rtol: float

    opt_kws: dict
        Keyword arguments to numeric_prox

    """

    assert behavior in ['ret', 'error', 'warn']

    errors = []
    passes = []
    for i, x in enumerate(values):

        # compute prox using function
        prox_out = func.prox(x=x, step=step)

        # comptue prox via numerical algorithm
        prox_baseline, opt_out = numeric_prox(func=func, x=x, step=step,
                                              init=prox_out,
                                              **opt_kws)
        if len(prox_baseline) == 1:
            prox_baseline = prox_baseline.item()

        # see how we did!
        did_pass = np.allclose(prox_out, prox_baseline, rtol=rtol, atol=atol)

        errs = {'mad': np.mean(abs(prox_out - prox_baseline)),
                'max': abs(prox_out - prox_baseline).max(),
                'l2': np.linalg.norm(prox_out - prox_baseline)}

        if verbosity >= 1:
            print('value ({}/{}) pass = {}'.
                  format(i + 1, len(values), did_pass))
            print(errs)
            print()

        if behavior == 'error':
            assert did_pass

        errors.append(errs)
        passes.append(did_pass)

    passes = np.array(passes)

    n_fails = sum(~passes)
    msg = '{}/{} prox evals failed: {}'.format(n_fails, len(passes), passes)
    if behavior == 'ret':
        return errors, passes

    if n_fails > 0:
        if behavior == 'warn':
            warn(msg)


# def check_equal(a, b, tol=1e-4, norm='max', avg=True):
#     """
#     Checks if two values are equal up to some tolerance.
#     """
#     assert norm in ['max', 1, 2]
#     diff = np.array(a).reshape(-1) - np.array(b).reshape(-1)

#     if norm == 'max':
#         val = max(abs(diff))

#     elif norm == 1 and avg:
#         val = np.mean(abs(diff))

#     elif norm == 1 and not avg:
#         val = np.sum(abs(diff))

#     elif norm == 2 and avg:
#         val = np.sqrt(np.mean((diff ** 2)))

#     elif norm == 2 and not avg:
#         val = np.sqrt(np.sum((diff ** 2)))

#     return val < tol
