
class a(object):
    def __init__(self, i):
        self.i = i

    def swap(self, othera):
        self.i, othera.i = othera.i, self.i

a1 = a(5)
a2 = a(6)
print(a1.i, a2.i)
a1.swap(a2)
print(a1.i, a2.i)