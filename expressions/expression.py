import abc
import cvxpy.constraints.constraint as c
import cvxpy.settings as s
from operators import BinaryOperator, UnaryOperator
import types
import cvxpy.interface.matrix_utilities as intf

class Expression(object):
    """
    A mathematical expression in a convex optimization problem.
    """
    __metaclass__ = abc.ABCMeta
    # TODO priority
    def __repr__(self):
        return self.name()

    # Returns string representation of the expression.
    @abc.abstractmethod
    def name(self):
        return NotImplemented

    # Returns a dict of term name to coefficient in the
    # expression and a set of possible expression sizes.
    # interface - the matrix interface to convert constants
    #             into a matrix of the target class.
    def coefficients(self, interface):
        return NotImplemented

    # Returns a dictionary of name to variable.
    # TODO necessary?
    def variables(self):
        vars = {}
        for term in self.terms():
            if isinstance(term, types.variable()):
                vars[term.id] = term
        return vars

    # Returns a list of all the objects in the expression.
    def terms(self):
        return NotImplemented

    # Returns the dimensions of the expression.
    @abc.abstractproperty
    def size(self):
        return NotImplemented

    # Returns the curvature of the expression.
    @abc.abstractproperty
    def curvature(self):
        return NotImplemented

    # Returns an affine expression and affine constraints
    # representing the expression, creating new variables if necessary.
    @abc.abstractmethod
    def canonicalize(self):
        return NotImplemented

    # Cast to Constant if not an Expression.
    @staticmethod
    def cast_to_const(expr):
        return expr if isinstance(expr, Expression) else types.constant()(expr)

    # Get the coefficient of the constant in the expression.
    @staticmethod 
    def constant(coeff_dict):
        return coeff_dict.get(s.CONSTANT, 0)

    """ Arithmetic operators """
    def __add__(self, other):
        return AddExpression(self, other)

    # Called for Number + Expression.
    def __radd__(self, other):
        return Expression.cast_to_const(other) + self

    def __sub__(self, other):
        return SubExpression(self, other)

    # Called for Number - Expression.
    def __rsub__(self, other):
        return Expression.cast_to_const(other) - self

    def __mul__(self, other):
        return MulExpression(self, other)

    # Called for Number * Expression.
    def __rmul__(self, other):
        return Expression.cast_to_const(other) * self

    def __neg__(self):
        return NegExpression(self)

    """ Comparison operators """
    def __eq__(self, other):
        return c.EqConstraint(self, other)

    def __le__(self, other):
        return c.LeqConstraint(self, other)

    def __ge__(self, other):
        return Expression.cast_to_const(other) <= self


class AddExpression(BinaryOperator, Expression):
    OP_NAME = "+"
    OP_FUNC = "__add__"
    # Evaluates the left hand and right hand expressions and sums the dicts.
    def coefficients(self, interface):
        lh = self.lh_exp.coefficients(interface)
        rh = self.rh_exp.coefficients(interface)
        # got this nice piece of code off stackoverflow http://stackoverflow.com/questions/1031199/adding-dictionaries-in-python
        return dict( (n, lh.get(n, 0) + rh.get(n, 0)) for n in set(lh)|set(rh) )

class SubExpression(BinaryOperator, Expression):
    OP_NAME = "-"
    OP_FUNC = "__sub__"
    def coefficients(self, interface):
        return (self.lh_exp + -self.rh_exp).coefficients(interface)

class MulExpression(BinaryOperator, Expression):
    OP_NAME = "*"
    OP_FUNC = "__mul__"
    # Evaluates the left hand and right hand expressions,
    # checks the left hand expression is constant,
    # and multiplies all the right hand coefficients by the left hand constant.
    def coefficients(self, interface):
        lh_coeff = self.lh_exp.coefficients(interface)
        rh_coeff = self.rh_exp.coefficients(interface)
        return dict((k,lh_coeff[s.CONSTANT]*v) for k,v in rh_coeff.items())

    # TODO scalar by vector/matrix
    @property
    def size(self):
        size = self.promoted_size()
        if size is not None:
            return size
        else:
            rh_rows,rh_cols = self.rh_exp.size
            lh_rows,lh_cols = self.lh_exp.size
            if lh_cols == rh_rows:
                return (lh_rows,rh_cols)
            else:
                raise Exception("'%s' has incompatible dimensions." % self.name())

    # Flips the curvature if the left hand expression is a negative scalar.
    # TODO is_constant instead of isinstance(...,Constant) using Sign
    @property
    def curvature(self):
        curvature = super(MulExpression, self).curvature
        if isinstance(self.lh_exp, types.constant()) and \
           self.lh_exp.size == (1,1) and \
           intf.scalar_value(self.lh_exp.value) < 0:
           return -curvature
        else:
            return curvature

class NegExpression(UnaryOperator, Expression):
    OP_NAME = "-"
    OP_FUNC = "__neg__"
    # Negate all coefficients.
    def coefficients(self, interface):
        return ( types.constant()(-1)*self.expr ).coefficients(interface)

class IndexExpression(Expression):
    # key - a tuple of integers.
    def __init__(self, expr, key):
        self.expr = expr
        self.key = key

    def name(self):
        return "%s[%s,%s]" % (self.expr.name(), self.key[0], self.key[1])

    # TODO slices
    def size(self):
        return (1,1)

    # Raise an Exception if the key is not a valid slice.
    def validate_key(self):
        rows,cols = self.expr.size
        if not (0 <= self.key[0] and self.key[0] < rows and \
                0 <= self.key[1] and self.key[1] < cols): 
           raise Exception("Invalid indices %s,%s for '%s'." % 
                (self.key[0], self.key[1], self.expr.name()))

    # TODO what happens to vectors/matrices of expressions?
    def curvature(self):
        return self.expr.curvature

    # TODO right place to error check?
    def canonicalize(self):
        self.validate_key()
        return (None, [])