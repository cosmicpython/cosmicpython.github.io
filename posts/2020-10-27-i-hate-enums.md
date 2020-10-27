title: Making Enums (as always, arguably) more Pythonic
author: Harry
image: crab_nebula_multiple.png
image_credit: https://commons.wikimedia.org/wiki/File:Crab_Nebula_in_Multiple_Wavelengths.png

OK this isn't really anything to do with software architecture, but:

> I hate [enums](https://docs.python.org/3/library/enum.html)!

I thought to myself, again and again, when having to deal with them recently.

Why?

```python
class BRAIN(Enum):
    SMALL = 'small'
    MEDIUM = 'medium'
    GALAXY = 'galaxy'
```

What could be wrong with that, I hear you ask?
Well, accuse me of wanting to _stringly type_ everything if you will,
but: those enums may look like strings but they aren't!

```python
assert BRAIN.SMALL == 'small'
# nope, <BRAIN.SMALL: 'small'> != 'small'

assert str(BRAIN.SMALL) == 'small'
# nope, 'BRAIN.SMALL' != 'small'

assert BRAIN.SMALL.value == 'small'
# finally, yes.
```

I imagine some people think this is a feature rather than a bug?  But for me
it's an endless source of annoyance.  They look like strings!  I defined them
as strings!  Why don't they behave like strings arg!

Just one common motivating example:  often what you want to do with those
enums is dump them into a database column somewhere. This not-quite-a-string
behaviour will cause your ORM or `db-api` library to complain like mad, and
no end of footguns and headscratching when writing tests, custom SQL, and so on.
At this point I'm wanting to throw them out and just use normal constants!

But, one of the nice promises from Python's `enum` module is that **it's iterable**.
So it's easy not just to refer to one constant,
but also to refer to the list of all allowed constants.  Maybe that's enough
to want to rescue it?

But, again, it doesn't quite work the way you might want it to:

```python
assert list(BRAIN) == ['small', 'medium', 'galaxy']  # nope
assert [thing for thing in BRAIN] == ['small', 'medium', 'galaxy']  # nope
assert [thing.value for thing in BRAIN] == ['small', 'medium', 'galaxy']  # yes
```

Here's a _truly_ wtf one:

```python
assert random.choice(BRAIN) in ['small', 'medium', 'galaxy']
# Raises an Exception!!!

  File "/usr/local/lib/python3.9/random.py", line 346, in choice
    return seq[self._randbelow(len(seq))]
  File "/usr/local/lib/python3.9/enum.py", line 355, in __getitem__
    return cls._member_map_[name]
KeyError: 2
```

I have no idea what's going on there. What we actually wanted was

```python
assert random.choice(list(BRAIN)) in ['small', 'medium', 'galaxy']
# which is still not true, but at least it doesn't raise an exception
```

Now the standard library does provide a solution
if you want to duck-type your enums to integers,
[IntEnum](https://docs.python.org/3/library/enum.html#derived-enumerations)


```python
class IBRAIN(IntEnum):
    SMALL = 1
    MEDIUM = 2
    GALAXY = 3

assert IBRAIN.SMALL == 1
assert int(IBRAIN.SMALL) == 1
assert IBRAIN.SMALL.value == 1
assert [thing for thing in IBRAIN] == [1, 2, 3]
assert list(IBRAIN) == [1, 2, 3]
assert [thing.value for thing in IBRAIN] == [1, 2, 3]
assert random.choice(IBRAIN) in [1, 2, 3]  # this still errors but:
assert random.choice(list(IBRAIN)) in [1, 2, 3]  # this is ok
```

That's all fine and good, but I don't _want_ to use integers.
I want to use strings, because then when I look in my database,
or in printouts, or wherever,
the values will make sense.

Well, the [docs say](https://docs.python.org/3/library/enum.html#others)
you can just subclass `str` and make your own `StringEnum` that will work just like `IntEnum`.
But it's LIES:

```python
class BRAIN(str, Enum):
    SMALL = 'small'
    MEDIUM = 'medium'
    GALAXY = 'galaxy'

assert BRAIN.SMALL.value == 'small'  # ok, as before
assert BRAIN.SMALL == 'small'  # yep
assert list(BRAIN) == ['small', 'medium', 'galaxy']  # hooray!
assert [thing for thing in BRAIN] == ['small', 'medium', 'galaxy']  # hooray!
random.choice(BRAIN)  # this still errors but ok i'm getting over it.

# but:
assert str(BRAIN.SMALL) == 'small'   #NOO!O!O!  'BRAIN.SMALL' != 'small'
# so, while BRAIN.SMALL == 'small', str(BRAIN.SMALL)  != 'small' aaaargh
```

So here's what I ended up with:

```python
class BRAIN(str, Enum):
    SMALL = 'small'
    MEDIUM = 'medium'
    GALAXY = 'galaxy'

    def __str__(self) -> str:
        return str.__str__(self)
```

* this basically avoids the need to use `.value` anywhere at all in your code
* enum values duck type to strings in the ways you'd expect
* you can iterate over brain and get string-likes out
  - altho `random.choice()` is still broken, i leave that as an exercise for the reader
* and type hints still work!

```python
# both of these type check ok
foo = BRAIN.SMALL  # type: str
bar = BRAIN.SMALL  # type: BRAIN
```

Example code is [in a Gist](https://gist.github.com/hjwp/405f04802ea558f042728ec5edbb4e62)
if you want to play around.
Let me know if you find anything better!
