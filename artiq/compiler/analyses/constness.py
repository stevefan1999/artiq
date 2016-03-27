"""
:class:`Constness` checks that no attribute marked
as constant is ever set.
"""

from pythonparser import algorithm, diagnostic
from .. import types

class Constness(algorithm.Visitor):
    def __init__(self, engine):
        self.engine = engine
        self.in_assign = False

    def visit_Assign(self, node):
        self.visit(node.value)
        self.in_assign = True
        self.visit(node.targets)
        self.in_assign = False

    def visit_AttributeT(self, node):
        self.generic_visit(node)
        if self.in_assign:
            typ = node.value.type.find()
            if types.is_instance(typ) and node.attr in typ.constant_attributes:
                diag = diagnostic.Diagnostic("error",
                    "cannot assign to constant attribute '{attr}' of class '{class}'",
                    {"attr": node.attr, "class": typ.name},
                    node.loc)
                self.engine.process(diag)
                return
