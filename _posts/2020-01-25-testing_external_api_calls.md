---
title: Writing tests for external API calls
layout: post
author: Harry
categories:
  - testing
tags:
  - tdd
  - fakes
  - mocks
  - adapters
---


Here's a common question from people doing testing in Python:

> How do I write tests for for code that calls out to a third-party API?

(with thanks to Brian Okken for suggesting the question).

In this article I'd like to outline several options, starting from the
most familiar (mocks) going out to the most architecture-astronautey,
and try and discuss the pros and cons of each one.  With luck I'll convince you
to at least try out some of the ideas near the end.


I'm going to use an example from the domain of logistics where we need to sync
shipments to a cargo provider's API, but you can really imagine any old API--a
payment gateway, an SMS notifications engine, a cloud storage provider.  Or you
can imagine an external dependency that's nothing to do with the web at all, just
any kind of external I/O dependency that's hard to unit test.


But to make things concrete, in our logistics example, we'll have a model of a
shipment which contains a number of order lines.  We also care about its
estimated time of arrival (`eta`) and a bit of jargon called the _incoterm_
(you don't need to understand what that is, I'm just trying to illustrate a bit
of real-life complexity, in this small example).

```python
@dataclass
class OrderLine:
    sku: str  # sku="stock keeping unit", it's a product id basically
    qty: int


@dataclass
class Shipment:
    reference: str
    lines: List[OrderLine]
    eta: Optional[date]
    incoterm: str

    def save(self):
        ...  # for the sake of the example, let's imagine the model
             # knows how to save itself to the DB.  like Django.

```


We want to sync our shipments model with a third party, the cargo freight
company, via their API. We have a couple of use cases: creating new shipments,
and checking for updated etas.


Let's say we have some sort of controller function that's in charge of doing this.  It
takes a dict mapping skus to quantities, creates our model objects, saves them, and
then calls a helper function to sync to the API.  Hopefully this sort of thing
looks familiar:

```python
def create_shipment(quantities: Dict[str, int], incoterm):
    reference = uuid.uuid4().hex[:10]
    order_lines = [OrderLine(sku=sku, qty=qty) for sku, qty in quantities.items()]
    shipment = Shipment(reference=reference, lines=order_lines, eta=None, incoterm=incoterm)
    shipment.save()
    sync_to_api(shipment)
```


How do we sync to the API?  A simple POST request, with a bit of datatype
conversion and wrangling.

```python
def sync_to_api(shipment):
    requests.post(f'{API_URL}/shipments/', json={
        'client_reference': shipment.reference,
        'arrival_date': shipment.eta.isoformat(),
        'products': [
            {'sku': ol.sku, 'quantity': ol.quantity}
            for ol in shipment.lines
        ]
    })
```

Not too bad!

How do we test it? In a case like this, the typical reaction is to reach for mocks,
and _as long as things stay simple_, it's pretty manageable


```python
def test_create_shipment_does_post_to_external_api():
    with mock.patch('controllers.requests') as mock_requests:
        shipment = create_shipment({'sku1': 10}, incoterm='EXW')
        expected_data = {
            'client_reference': shipment.reference,
            'arrival_date': None,
            'products': [{'sku': 'sku1', 'quantity': 10}],
        }
        assert mock_requests.post.call_args == mock.call(
            API_URL + '/shipments/', json=expected_data
        )
```

And you can imagine adding a few more tests, perhaps one that checks that we do
the date-to-isoformat conversion correctly, maybe one that checks we can handle
multiple lines.  Three tests, one mock each, we're ok.

The trouble is that it never stays quite that simple does it?  For example,
the cargo company may already have a shipment on record, because reasons.
And if you do a POST when something already exists, then bad things happen.
So we first need to check whether they have a shipment on file, using
a GET request, and then we either do a POST if it's new, or a PUT for
an existing one:

```python
def sync_to_api(shipment):
    external_shipment_id = get_shipment_id(shipment.reference)
    if external_shipment_id is None:
        requests.post(f'{API_URL}/shipments/', json={
            'client_reference': shipment.reference,
            'arrival_date': shipment.eta,
            'products': [
                {'sku': ol.sku, 'quantity': ol.quantity}
                for ol in shipment.lines
            ]
        })

    else:
        requests.put(f'{API_URL}/shipments/{external_shipment_id}', json={
            'client_reference': shipment.reference,
            'arrival_date': shipment.eta,
            'products': [
                {'sku': ol.sku, 'quantity': ol.quantity}
                for ol in shipment.lines
            ]
        })


def get_shipment_id(our_reference) -> Optional[str]:
    their_shipments = requests.get(f"{API_URL}/shipments/").json()['items']
    return next(
        (s['id'] for s in their_shipments if s['client_reference'] == our_reference),
        None
    )
```

And as usual, complexity creeps in:

* Because things are never easy, the third party has different reference
  numbers to us, so we need the `get_shipment_id()` function that finds the
  right one for us

* And we need to use POST if it's a new shipment, or PUT if it's an existing one.

Already you can imagine we're going to need to write quite a few tests to cover
all these options.  Here's just one, as an example:

```python
def test_does_PUT_if_shipment_already_exists():
    with mock.patch('controllers.uuid') as mock_uuid, mock.patch('controllers.requests') as mock_requests:
        mock_uuid.uuid4.return_value.hex = 'our-id'
        mock_requests.get.return_value.json.return_value = {
            'items': [{'id': 'their-id', 'client_reference': 'our-id'}]
        }

        shipment = create_shipment({'sku1': 10}, incoterm='EXW')
        assert mock_requests.post.called is False
        expected_data = {
            'client_reference': 'our-id',
            'arrival_date': None,
            'products': [{'sku': 'sku1', 'quantity': 10}],
        }
        assert mock_requests.put.call_args == mock.call(
            API_URL + '/shipments/their-id/', json=expected_data
        )
```

...and our tests are getting less and less pleasant.  Again, the details don't
matter too much, the hope is that this sort of test ugliness is familiar.


And this is only the beginning, we've shown an API integration that only cares
about writes, but what about reads?  Say we want to poll our third party api
now and again to get updated etas for our shipments.  Depending on the eta, we
have some business logic about notifying people of delays...


```python
# another example controller,
# showing business logic getting intermingled with API calls

def get_updated_eta(shipment):
    external_shipment_id = get_shipment_id(shipment.reference)
    if external_shipment_id is None:
        logging.warning('tried to get updated eta for shipment %s not yet sent to partners', shipment.reference)
        return

    [journey] = requests.get(f"{API_URL}/shipments/{external_shipment_id}/journeys").json()['items']
    latest_eta = journey['eta']
    if latest_eta == shipment.eta:
        return
    logging.info('setting new shipment eta for %s: %s (was %s)', shipment.reference, latest_eta, shipment.eta)
    if shipment.eta is not None and latest_eta > shipment.eta:
        notify_delay(shipment_ref=shipment.reference, delay=latest_eta - shipment.eta)
    if shipment.eta is None and shipment.incoterm == 'FOB' and len(shipment.lines) > 10:
        notify_new_large_shipment(shipment_ref=shipment.reference, eta=latest_eta)

    shipment.eta = latest_eta
    shipment.save()
```

I haven't coded up what all the tests would look like, but you could imagine them:

1. a test that if the shipment does not exist, we log a warning.  Needs to mock `requests.get` or `get_shipment_id()`
1. a test that if the eta has not changed, we do nothing.  Needs two different mocks on `requests.get`
1. a test for the error case where the shipments api has no journeys
1. a test for the edge case where the shipment has multiple journeys
1. a tests to check that if the eta is is later than the current one, we do a
   notification.
1. and a test of the converse, no notification if eta sooner
1. a test for the large shipments notification
1. and a test that we only do that one if necessary
1. and a general test that we update the local eta and save it.
1. ...I'm sure we can imagine some more.

And each one of these tests needs to set up three or four mocks.  We're getting
into what Ed Jung calls [Mock Hell](https://www.youtube.com/watch?v=CdKaZ7boiZ4).

On top of our tests being hard to read and write, they're also brittle.  If we
change the way we import, from `import requests` to `from requests import get`
(not that you'd ever do that, but you get the point), then all our mocks break.
If you want a more plausible example, perhaps we decide to stop using
`requests.get()` because we want to use `requests.Session()` for whatever
reason.

> The point is that `mock.patch` ties you to specific implementation details

And we haven't even spoken about other kinds of tests.  To reassure yourself
that things _really_ work, you're probably going to want an integration test or
two, and maybe an E2E test.


Here's a little recap of the pros and cons of the mocking approach.  We'll
have one of these each time we introduce a new option.

#### Mocking and patching: tradeoffs

##### Pros:

* no change to client code
* low effort
* it's familiar to (most? many?) devs

##### Cons:

* tightly coupled
* brittle.  `requests.get` -> `requests.Session().get` will break it.
* need to remember to `@mock.patch` every single test that might
 end up invoking that api
* easy to mix together business logic and I/O concerns
* probably need integration & E2E tests as well.




## SUGGESTION: Build an Adapter (a wrapper for the external API)

We really want to disentangle our business logic from our API integration.
Building an abstraction, a wrapper around the API that just exposes nice,
readable methods for us to call in our code.

> We call it an "adapter" in [ports & adapters](https://github.com/cosmicpython/book/blob/master/chapter_02_repository.asciidoc#what_is_a_port_and_what_is_an_adapter) sense,
> but you don't have to go full-on hexagonal architecture to use
> this pattern.



```python
class RealCargoAPI:
    API_URL = 'https://example.org'

    def sync(self, shipment: Shipment) -> None:
        external_shipment_id = self._get_shipment_id(shipment.reference)
        if external_shipment_id is None:
            requests.post(f'{self.API_URL}/shipments/', json={
              ...

        else:
            requests.put(f'{self.API_URL}/shipments/{external_shipment_id}/', json={
              ...


    def _get_shipment_id(self, our_reference) -> Optional[str]:
        try:
            their_shipments = requests.get(f"{self.API_URL}/shipments/").json()['items']
            return next(
              ...
        except requests.exceptions.RequestException:
            ...

```

Now how do our tests look?


```python
def test_create_shipment_syncs_to_api():
    with mock.patch('controllers.cargo_api') as mock_cargo_api:
        shipment = create_shipment({'sku1': 10}, incoterm='EXW')
        assert mock_cargo_api.sync.call_args == mock.call(shipment)
```

Much more manageable!


But:

* we still have the `mock.patch` brittleness, meaning if we change our mind about how
  we import things, we need to change our mocks

* and we still need to test the api adapters itself:


```python
def test_sync_does_post_for_new_shipment():
    api = RealCargoAPI()
    line = OrderLine('sku1', 10)
    shipment = Shipment(reference='ref', lines=[line], eta=None, incoterm='foo')
    with mock.patch('cargo_api.requests') as mock_requests:
        api.sync(shipment)

        expected_data = {
            'client_reference': shipment.reference,
            'arrival_date': None,
            'products': [{'sku': 'sku1', 'quantity': 10}],
        }
        assert mock_requests.post.call_args == mock.call(
            API_URL + '/shipments/', json=expected_data
        )
```


# SUGGESTION: Use (only?) integration tests to test your Adapter


Now we can test our adapter separately from our main application code, we
can have a think about what the best way to test it is.  Since it's just
a thin wrapper around an external system, the best kinds of tests are integration
tests:

```python
def test_can_create_new_shipment():
    api = RealCargoAPI('https://sandbox.example.com/')
    line = OrderLine('sku1', 10)
    ref = random_reference()
    shipment = Shipment(reference=ref, lines=[line], eta=None, incoterm='foo')

    api.sync(shipment)

    shipments = requests.get(api.api_url + '/shipments/').json()['items']
    new_shipment = next(s for s in shipments if s['client_reference'] == ref)
    assert new_shipment['arrival_date'] is None
    assert new_shipment['products'] == [{'sku': 'sku1', 'quantity': 10}]


def test_can_update_a_shipment():
    api = RealCargoAPI('https://sandbox.example.com/')
    line = OrderLine('sku1', 10)
    ref = random_reference()
    shipment = Shipment(reference=ref, lines=[line], eta=None, incoterm='foo')

    api.sync(shipment)

    shipment.lines[0].qty = 20

    api.sync(shipment)

    shipments = requests.get(api.api_url + '/shipments/').json()['items']
    new_shipment = next(s for s in shipments if s['client_reference'] == ref)
    assert new_shipment['products'] == [{'sku': 'sku1', 'quantity': 20}]
```

That relies on your third-party api having a decent sandbox that you can test against.
You'll need to think about:

* how do you clean up? Running dozens of tests dozens of times a day in dev
  and CI will start filling the sandbox with test data.

* is the sandbox slow and annoying to test against?  are devs going to be
  annoyed at waiting for integration tests to finish on their machines, or
  in CI?

* is the sandbox flakey at all?  have you now introduced randomly-failing
  tests in your build?


#### Adapter around api, with integration tests, tradeoffs:

##### Pros:

* obey the "don't mock what you don't own" rule.
* we present a simple api, which is easier to mock
* we stop messing about with mocks like `requests.get.return_value.json.return_value`
* if we ever change our third party, there's a good chance that the API of our
  adapter will _not_ change.  so our core app code (and its tests) don't need
  to change.

##### Cons:
* we've added an extra layer in our application code, which for simple cases
  might be unnecessary complexity
* integration tests are strongly dependent on your third party providing a good
  test sandbox
* integration tests may be slow and flakey


## OPTION: vcr.py

I want to give a quick nod to [vcr.py](https://vcrpy.readthedocs.io/en/latest/)
at this point.

VCR is a very neat solution. It lets you run your tests against a real
endpoint, and then it captures the outgoing and incoming requests, and
serializes them to disk. Next time you run the tests, it intercepts your HTTP
requests, compares them against the saved ones, and replays past responses.

The end result is that you have a way of running integration tests with
realistic simulated responses, but without actually needing to talk to
an external third party.

At any time you like, you can also trigger a test run against the real API,
and it will update your saved response files.  This gives you a way of
checking whether things have changed on a periodic basis, and updating
your recorded responses when they do.

As I say it's a very neat solution, and I've used it successfully, but it does
have some drawbacks:

* Firstly the workflow can be quite confusing.  While you're still evolving
  your integration, your code is going to change, and the canned responses too,
  and it can be hard to keep track of what's on disk, what's fake and what's not.
  One person can usually wrap their head around it, but it's a steep learning
  curve for other members of the team.  That can be particularly painful if
  it's code that only gets changed infrequently, because it's long enough for
  everyone to forget.

* Secondly, `vcr.py` is tricky to configure when you have randomised data in
  your requests (eg unique ids).  By default it looks for requests that are
  exactly the same as the ones it's recorded. You can configure "matchers" to
  selectively ignore certain fields when recognising requests, but that
  only deals with half the problem.

* If you send out a POST and follow up with a GET for the same ID, you might be
  able to configure a matcher to ignore the ID in the requests, but the
  responses will still contain the old IDs.  That will break any logic on your
  own side that's doing any logic based on those IDs.

#### vcr.py tradeoffs

##### Pros:
* gives you a way of isolating tests from external dependencies by replaying canned responses
* can re-run against real API at any time
* no changes to application code required

##### Cons:
* can be tricky for team-members to understand
* dealing with randomly-generated data is hard
* challenging to simulate state-based workflows



## OPTION: Build your own fake for integration tests

We're into dangerous territory now,  the solution we're about to present is not
necessarily a good idea in all cases.  Like any solution you find on random blogs
on the internet I suppose, but still.

So when might you think about doing this?

* if the integration is not core to your application, i.e it's an incidental feature
* if the bulk of the code you write, and the feedback you want, is not about
  integration issues, but about other things in your app
* if you really can't figure out how to fix the problems with your integration
  tests another way (retries? perhaps they'd be a good idea anyway?)

Then you might consider building your own fake version of the external API.  Then
you can spin it up in a docker container, run it alongside your test code, and
talk to that instead of the real API.

Faking a third party is often quite simple.  A REST API around a CRUD data model
might just pop json objects in an out of an in-memory dict, for example:

```python
from flask import Flask, request

app = Flask('fake-cargo-api')

SHIPMENTS = {}  # type: Dict[str, Dict]

@app.route('/shipments/', methods=["GET"])
def list_shipments():
    print('returning', SHIPMENTS)
    return {'items': list(SHIPMENTS.values())}


@app.route('/shipments/', methods=["POST"])
def create_shipment():
    new_id = uuid.uuid4().hex
    refs = {s['client_reference'] for s in SHIPMENTS.values()}
    if request.json['client_reference'] in refs:
        return 'already exists', 400
    SHIPMENTS[new_id] = {'id': new_id, **request.json}
    print('saved', SHIPMENTS)
    return 'ok', 201


@app.route('/shipments/<shipment_id>/', methods=["PUT"])
def update_shipment(shipment_id):
    existing = SHIPMENTS[shipment_id]
    SHIPMENTS[shipment_id] = {**existing, **request.json}
    print('updated', SHIPMENTS)
    return 'ok', 200
```


This doesn't mean you _never_ test against the third-party API, but
you've now given yourself the _option_ not to.

* perhaps you test against the real API in CI, but not in dev

* perhaps you have a way of marking certain PRs as needing
  "real" api integration tests

* perhaps you have some logic in CI that looks at what code has
  changed in a given PR, tries to spot anything to do with the
  third party api, and only _then_ runs against the real API


## OPTION: Contract tests

I'm not sure if "contract tests" is a real bit of terminology, but the idea is
to test that the behaviour of the third party API conforms to a contract.  That
it does what you need it to do.

They're different from integration tests because you may not be testing
your adapter itself, and they tend to be against a single endpoint at a time.
Things like:

* checking the format and datatypes of data for given endpoints.  are all
  the fields you need there?

* if the third party api has bugs you need to work around, you might repro
  that bug in a test, so that you know if they ever fix it

These tests tend to be more lightweight than integration tests, in that
they are often read-only, so they suffer less from problems related to
clean-up.  You might decide they're useful in addition to integration tests,
or they might be a useful backup option if proper integration tests aren't
possible.  In a similar way, you probably want ways of _selectively_ running
your contract tests against your third party.

> you can also run your contract tests against your fake api.

When you run your contract tests against your own fake api as well as
against the real thing, you're confirming the quality of your fake.
Some people call this [verified fakes](https://pythonspeed.com/articles/verified-fakes/)
(see also ["stop mocking and start testing"](https://nedbatchelder.com/blog/201206/tldw_stop_mocking_start_testing.html).)
[](https://nedbatchelder.com/blog/201206/tldw_stop_mocking_start_testing.html)


## OPTION: DI

We still have the problem that using `mock.patch` ties us to specific
ways of importing our adapter.  We also need to remember to set up
that mock on _any_ test that might use the third party adapter.

> Making the dependency explicit and using DI solves these problems

Again, we're in dangerous territory here. Python people are skeptical
of DI, and neither of these problems is _that_ big of a deal.  But
DI does buy us some nice things, so read on with an open mind.


First, you might like to define an interface for your dependency explicitly.
You could use an `abc.ABC`, or if you're anti-inheritance, a newfangled
`typing.Protocol`:

```python
class CargoAPI(Protocol):

    def get_latest_eta(self, reference: str) -> date:
        ...

    def sync(self, shipment: Shipment) -> None:
        ...
```


Now we can add our explicit dependency where it's needed, replacing
a hardcoded `import` with a new, explicit argument to a function somewhere.
Possibly event with a type hint:

```python
def create_shipment(
    quantities: Dict[str, int],
    incoterm: str,
    cargo_api: CargoAPI
) -> Shipment:
    ...
    # rest of controller code essentially unchanged.
```

What effect does that have on our tests?  Well, instead of needing to
call `with mock.patch()`, we can create a standalone mock, and pass it
in:


```python
def test_create_shipment_syncs_to_api():
    mock_api = mock.Mock()
    shipment = create_shipment({'sku1': 10}, incoterm='EXW', cargo_api=mock_api)
    assert mock_api.sync.call_args == mock.call(shipment)
```

#### DI tradeoffs

##### Pros:

* no need to _remember_ to do `mock.patch()`, the function arguments
  always require the dependency

##### Cons

* we've added an "unnecessary" extra argument to our function


> This change of an `import` to an explicit dependency is memorably advocated
> for in Yeray Díaz's talk [import as an antipattern](https://www.youtube.com/watch?v=qkGxy4c64Jg)



So far you may think the pros aren't enough of a wow to justify the con?
Well, if we take it one step further and really commit to DI, you may yet get
on board.


## OPTION: build your own fake for unit tests

Just like we can build our own fake for integration testing,
we can build our own fake for unit tests too.  Yes it's more
lines of code than `mock_api = mock.Mock()`, but it's not a
lot:

```python
class FakeCargoAPI:
    def __init__(self):
        self._shipments = {}

    def get_latest_eta(self, reference) -> date:
        return self._shipments[reference].eta

    def sync(self, shipment: Shipment):
        self._shipments[shipment.reference] = shipment

    def __contains__(self, shipment):
        return shipment in self._shipments.values()
```

The fake is in-memory and in-process this time, but again, it's just a
thin wrapper around some sort of container, a dict in this case.

`get_latest_eta()` and `sync()` are the two methods we need to define
to make it emulate the real api (and comply with the `Protocol`).

> `mypy` will tell you when you get this right, or if you ever need to change it

The `__contains__` is just a bit of syntactic sugar that lets us use
`assert in` in our tests, which looks nice.  It's a Bob thing.

```python
def test_create_shipment_syncs_to_api():
    api = FakeCargoAPI()
    shipment = create_shipment({'sku1': 10}, incoterm='EXW', cargo_api=api)
    assert shipment in api
```

Why bother with this?

#### Handrolled fakes for unit tests, the tradeoffs

##### Pros:
* tests can be more readable, no more `mock.call_args == call(foo,bar)` stuff
* 👉Our fake exerts design pressure on our Adapter's API👈

##### Cons:
* more code in tests
* need to keep the fake in sync with the real thing

The design pressure is the killer argument in our opinion.  Because hand-rolling
a fake _is_ more effort, it forces us to think about the API of our adapter,
and it gives us an incentive to keep it simple.

If you think back to our initial decision to build a wrapper, in our toy example
it was quite easy to decide what the adapter should look like, we just needed
one public method called `sync()`.  In real life it's sometimes harder to figure
out what belongs in an adapter, and what stays in business logic.   By forcing
ourselves to build a fake, we get to really see the shape of the thing that
we're abstracting out.

* See this excerpt from our book in which we talk about
  [heuristics for abstracting out dependencies](http://www.obeythetestinggoat.com/new-book-excerpt-abstractions.html).


> For bonus points, you can even share code between the fake class you use
> for your unit tests, and the fake you use for your integration tests.




## Recap

* As soon as your integration with an external API gets beyond the trivial,
  mocking and patching starts to be quite painful

* Consider abstracting out a wrapper around your API

* Use integration tests to test your adapter, and unit tests for your
  business logic (and to check that you call your adapter correctly)

* Consider writing your own fakes for your unit tests.  They will
  help you find a good abstraction.

* If you want a way for devs or CI to run tests without depending
  on the external API, consider also writing a fully-functional fake of the
  third-party API (an actual web server).

* For bonus points, the two fakes can share code.

* Selectively running integration tests against both the fake and the real API
  can validate that both continue to work over time.

* You could also consider adding more targeted "contract tests" for this purpose.


> If you'd like to play around with the code from this blog post, you can
> [check it out here](https://github.com/cosmicpython/code/tree/blogpost-testing-api)


## Prior art

* [Mock Hell](https://www.youtube.com/watch?v=CdKaZ7boiZ4) by Ed Jung
* [Stop mocking and start testing](https://nedbatchelder.com/blog/201206/tldw_stop_mocking_start_testing.html) by Augie Fackler Nathaniel Manista (and summarised by Ned Batchelder)
* [Verified fakes](https://pythonspeed.com/articles/verified-fakes/) by Itamar Turner-Trauring
* [Hoist your I/O](https://www.youtube.com/watch?v=PBQN62oUnN8) by Brandon Rhodes

