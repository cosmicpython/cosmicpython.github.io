---
title: Testing external API calls
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

## Notes

common question, how do i write tests for external api calls


Let's take an example to do with logistics, we have a model of a shipment which contains a number
of order lines.  We also care about its estimated time of arrival (`eta`) and a bit of jargon
called the "incoterm" (you don't need to understand what that is, I'm just trying to illustrate
a bit of real-life complexity, in this small example).

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


We want to sync our shipments model with a third party, the cargo freight company, via their API.
We have a couple of use cases, new shipment creation, and checking for updated etas:


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


How do we sync to the API?  a simple post request, with a bit of datatype conversion and wrangling.

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

Not too bad!  In a case like this, the typical reaction is to reach for mocks,
and _as long as things stay simple_, it's pretty manageable


```python
def test_create_shipment_does_post_to_external_api():
    with mock.patch('use_cases.requests') as mock_requests:
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

And you can imagine adding a few more tests, perhaps one that checks that
we do the date-to-isoformat conversion correctly, maybe one that checks we can handle multiple
lines.  Three tests, one mock each, we're ok.

The trouble is that it never stays quite that simple does it?  For example,
the cargo company may already have a shipment on record, because reasons.
And if you do a POST when something already exists, then bad things happen.
So we first need to check whether they have a shipment on file, using
a GET request, and then we either do a POST if it's new, or a PUT for
an existing one:

```python
def get_shipment_id(our_reference) -> Optional[str]:
    their_shipments = requests.get(f"{API_URL}/shipments/").json()['items']
    return next(
        (s['id'] for s in their_shipments if s['client_reference'] == our_reference),
        None
    )



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



```

* because things are never easy, the third party has different reference numbers to us,
  so we need the `get_shipment_id()` function that finds the right one for us

* and we need to use POST if it's a new shipment, or PUT if it's an existing one.
  don't ask why they would know about a shipment before we do, it happens.

Already you can imagine we're going to need to write quite a few tests to cover all these options.

```python
def test_does_PUT_if_shipment_already_exists():
    with mock.patch('use_cases.uuid') as mock_uuid, mock.patch('use_cases.requests') as mock_requests:
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

and our tests are getting less and less pleasant.  Again, the details don't matter too
much, the hope is that this sort of test ugliness is familiar.


And this is only the beginning, we've shown an API integration that only cares about writes,
but what about reads?  Say we want to poll our third party api now and again to get updated etas
for ours shipments.  Depending on the eta, we have some business logic about notifying
people of delays...


```python
def get_updated_eta(shipment):
    external_shipment_id = get_shipment_id(shipment.reference)
    if external_shipment_id is None:
        logging.warning(
            'tried to get updated eta for shipment %s not yet sent to partners',
            shipment.reference
        )
        return

    [journey] = requests.get(f"{API_URL}/shipments/{external_shipment_id}/journeys").json()['items']
    latest_eta = journey['eta']
    if latest_eta == shipment.eta:
        return
    logging.info(
        'setting new shipment eta for %s: %s (was %s)',
        shipment.reference, latest_eta, shipment.eta
    )
    if shipment.eta is not None and latest_eta > shipment.eta:
        notify_delay(shipment_ref=shipment.reference, delay=latest_eta - shipment.eta)
    if shipment.eta is None and shipment.incoterm == 'FOB' and len(shipment.lines) > 10:
        notify_new_large_shipment(shipment_ref=shipment.reference, eta=latest_eta)

    shipment.eta = latest_eta
    shipment.save()
```

I haven't coded up what all the tests would look like, but you could imagine them:

* a test that if the shipment does not exist, we log a warning.  Needs to mock `requests.get` or `get_shipment_id()`
* a test that if the eta has not changed, we do nothing.  Needs two different mocks on `requests.get`
* a test for the error case where the shipments api has no journeys
* a test for the edge case where the shipment has multiple journeys
* two tests to check that if the eta is is later than the current one, we do a notification.
* two test for the large shipments notification
* and a general test that we update the local eta and save it.


And each one of these tests needs to set up three or four mocks.  We're getting into what Ed Jung
calls [Mock Hell](https://www.youtube.com/watch?v=CdKaZ7boiZ4).

On top of our tests being hard to read and write, they're also brittle.  If we change the way we
import, from `import requests` to `from requests import get` (not that you'd ever do that, but
you get the point), then all our mocks break.  If you want a more plausible example,
perhaps we decide to stop using `requests.get()` because we want to use
`requests.Session()` for whatever reason.  

> The point is that `mock.patch` ties you to specific implementation details


pros:
* no change to client code
* low effort
* it's familiar to (most? many?) devs

cons:
* tightly coupled
* brittle.  requests.get -> requests.Session().get will break it.
* need to remember to `@mock.patch` every single test that might
 end up invoking that api


- could mention vcr.py here.  ingenious but i've found it confuses ppl.

* and you still need an integration test or two, and maybe an E2E test.
  so you need a sandbox, or some way of faking it out irl


# SUGGESTION: Build an Adapter (a wrapper for the external API)

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
    with mock.patch('use_cases.cargo_api') as mock_cargo_api:
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

* how do you clean up?  running dozens of tests dozens of times a day in dev
  and CI will start filling the sandbox with test data. s i can't, how much
  data will start piling up in the sandbox

* is the sandbox slow and annoying to test against?  are devs going to be
  annoyed at waiting for integration tests to finish on their machines, or
  in CI?

* is the sandbox flakey at all?  have you now introduced randomly-failing
  tests in your build?


Adapter around api, with integration tests

Pros:

* obey the "don't mock what you don't own" rule.
* we present a simple api, which is easier to mock
* we stop messing about with mocks like `requests.get.return_value.json.return_value`
* if we ever change our third party, there's a good chance that the API of our
  adapter will _not_ change.  so our core app code (and its tests) don't need
  to change.

Cons:
* we've added an extra layer in our application code, which for simple cases might be unnecessary complexity
* integration tests are strongly dependent on your third party providing a good test sandbox
* integration tests may be slow and flakey




# OPTION: Build your own fake for integration tests

We're into dangerous territory now,  the solution we're about to present is not
necessarily a good idea in all cases.  Like any solution you find on random blogs
on the internet I suppose, but still.

So when might you think about doing this?

* if the integration is not core to your application, ie it's an incidental feature
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


# OPTION: Contract tests

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
clean-up


# OPTION: DI 

We still have the problem that using `mock.patch` ties us to specific
ways of importing our adapter.  We also need to remember to set up
that mock on _any_ test that might use the third party adapter.

> Making the dependency explicit and using DI solves these problems

Again, we're in dangerous territory here.  Python people are skeptical
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
```

> This change of an `import` to an explicit dependency is memorably advocated
> for in Yeray Díaz's talk [Import as an antipattern](https://www.youtube.com/watch?v=qkGxy4c64Jg)


What effect does that have on our tests?  Well, instead of needing to
call `with mock.patch()`, we can create a standalone mock, and pass it
in:


```python
def test_create_shipment_syncs_to_api():
    mock_api = mock.Mock()
    shipment = create_shipment({'sku1': 10}, incoterm='EXW', cargo_api=mock_api)
    assert mock_api.sync.call_args == mock.call(shipment)
```

Pros:
* no need to _remember_ to do `mock.patch()`, the function arguments
  always require the dependency

Cons
* we've added an "unnecessary" extra argument to our function


So far you may think the pros isn't enough of a wow to justify the con?
Well, if we take it one step further and really commit, you may yet get
on board.

# OPTION: build your own fake for unit tests

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

Pros:
* tests can be more readable, no more `mock.call_args == call(foo,bar)` stuff
* _Our fake exercises design pressure on our Adapter's API_

Cons:
* more code in tests
* need to keep the fake in sync with the real thing

The design pressure is the killer argument in our opinion.  Because hand-rolling
a fake _is_ more effort, it forces us to think about the API of our adapter,
and it gives us an incentive to keep it simple.

(callback to initial decision to build a wrapper.  the fake helps do it right)

* link to [example code](https://github.com/cosmicpython/code/tree/blogpost-testing-api)


# TODOS:

* link to Brandon [Hoist your I/O](https://www.youtube.com/watch?v=PBQN62oUnN8) video?

