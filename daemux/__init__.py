'''Daemux.

>>> import daemux
>>> yes = daemux.start('yes')
>>> yes.status()
'running'
>>> yes.stop()
'''

if __name__ == '__main__':
    import doctest
    doctest.testmod()
