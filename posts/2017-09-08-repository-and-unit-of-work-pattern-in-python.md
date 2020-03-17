title: Repository and Unit of Work Pattern
author: Bob

---

In the previous part
([Introducing Command Handler]( ./blog/2017-09-07-introducing-command-handler.html))
of this series we built a toy system that could add a new Issue to an IssueLog, but
had no real behaviour of its own, and would lose its data every time the
application restarted. We're going to extend it a little by introducing some
patterns for persistent data access, and talk a little more about the ideas
underlying ports and adapters architectures. To recap, we're abiding by three
principles:

 1. Clearly define the boundaries of our use cases.
 2. Depend on abstractions, not on concrete implementation.
 3. Identify glue code as distinct from domain logic and put it into its own
    layer.

In our command handler, we wrote the following code:

```python
reporter = IssueReporter(cmd.reporter_name, cmd.reporter_email)
issue = Issue(reporter, cmd.problem_description)
issue_log.add(issue)
```

The IssueLog is a term from our conversation with the domain expert. It's the
place that they record the list of all issues. This is part of the jargon used
by our customers, and so it clearly belongs in the domain, but it's also the
ideal abstraction for a data store. How can we modify the code so that our newly
created Issue will be persisted? We don't want our IssueLog to depend on the
database, because that's a violation of principle #2. This is the question that
leads us to the ports & adapters architecture.

In a ports and adapters architecture, we build a pure domain that exposes ports.
A port is a way for data to get into, or out of, the domain model. In this
system, the IssueLog is a port. Ports are connected to the external world by
Adapters. In the previous code sample, the FakeIssueLog is an adapter: it
provides a service to the system by implementing an interface.

Let's use a real-world analogy. Imagine we have a circuit that detects current
over some threshold. If the threshold is reached, the circuit outputs a signal.
Into our circuit we attach two ports, one for current in, and one for current
out. The input and output channels are part of our circuit: without them, the
circuit is useless.

```python
class ThresholdDetectionCircuit:

    arbitrary_threshold = 4

    def __init__(self, input: ReadablePort, output: WriteablePort):
        self.input = input
        self.output = output
        
    def read_from_input(self):
        next_value = self.input.read()
        if next_value > self.arbitrary_threshold:
            self.output.write(1)
```

Because we had the great foresight to use standardised ports, we can plug any
number of different devices into our circuit. For example, we could attach a
light-detector to the input and a buzzer to the output, or we could attach a
dial to the input, and a light to the output, and so on.

```python
class LightDetector(ReadablePort):
    def read(self):
        return self.get_light_amplitude()
        
class Buzzer(WriteablePort):
    def write(self, value):
        if value > 0:
            self.make_infuriating_noise()
            
            
class Dial(ReadablePort):
    def read(self):
        return self.current_value

class Light(self):
    def write(self, value):
        if value > 0:
            self.on = True
        else:
            self.on = False
```


Considered in isolation, this is just an example of good OO practice: we are
extending our system through composition. What makes this a ports-and-adapters
architecture is the idea that there is an internal world consisting of the
domain model (our ThresholdDetectionCircuit), and an external world that drives
the domain model through well-defined ports. How does all of this relate to
databases?


```python
from SqlAlchemy import Session

class SqlAlchemyIssueLog (IssueLog):
    
    def __init__(self, session: Session):
        self.session = session
    
    def add(self, issue):
        self.session.add(issue)


class TextFileIssueLog (IssueLog):
    
    def __init__(self, path):
        self.path = path
        
    def add(self, issue):
        with open(self.path, 'w') as f:
            json.dump(f)
```

By analogy to our circuit example, the IssueLog is a WriteablePort - it's a way
for us to get data out of the system. SqlAlchemy and the file system are two
types of adapter that we can plug in, just like the Buzzer or Light classes. In
fact, the IssueLog is an instance of a common design pattern: it's a Repository
[https://martinfowler.com/eaaCatalog/repository.html]. A repository is an object
that hides the details of persistent storage by presenting us with an interface
that looks like a collection. We should be able to add new things to the
repository, and get things out of the repository, and that's essentially it.

Let's look at a simple repository pattern.

```python
class FooRepository:
    def __init__(self, db_session):
        self.session = db_session
        
    def add_new_item(self, item):
        self.db_session.add(item)
        
    def get_item(self, id):
        return self.db_session.get(Foo, id)
        
    def find_foos_by_latitude(self, latitude):
        return self.session.query(Foo).\
                filter(foo.latitude == latitude)
```

We expose a few methods, one to add new items, one to get items by their id, and
a third to find items by some criterion. This FooRepository is using a 
SqlAlchemy session
[http://docs.sqlalchemy.org/en/latest/orm/session_basics.html]  object, so it's
part of our Adapter layer. We could define a different adapter for use in unit
tests.

```python
class FooRepository:
    def __init__(self, db_session):
        self.items = []
        
    def add_new_item(self, item):
        self.items.append(item)
        
    def get_item(self, id):
        return next((item for item in self.items 
                          if item.id == id))
        
    def find_foos_by_latitude(self, latitude):
        return (item for item in self.items
                     if item.latitude == latitude)
```

This adapter works just the same as the one backed by a real database, but does
so without any external state. This allows us to test our code without resorting
to Setup/Teardown scripts on our database, or monkey patching our ORM to return
hard-coded values. We just plug a different adapter into the existing port. As
with the ReadablePort and WriteablePort, the simplicity of this interface makes
it simple for us to plug in different implementations.

The repository gives us read/write access to objects in our data store, and is
commonly used with another pattern, the Unit of Work
[https://martinfowler.com/eaaCatalog/unitOfWork.html]. A unit of work represents
a bunch of things that all have to happen together. It usually allows us to
cache objects in memory for the lifetime of a request so that we don't need to
make repeated calls to the database. A unit of work is responsible for doing
dirty checks on our objects, and flushing any changes to state at the end of a
request.

What does a unit of work look like?

```python
class SqlAlchemyUnitOfWorkManager(UnitOfWorkManager):
    """The Unit of work manager returns a new unit of work. 
       Our UOW is backed by a sql alchemy session whose 
       lifetime can be scoped to a web request, or a 
       long-lived background job."""
    def __init__(self, session_maker):
        self.session_maker = session_maker

    def start(self):
        return SqlAlchemyUnitOfWork(self.session_maker)
   
   
class SqlAlchemyUnitOfWork(UnitOfWork):
    """The unit of work captures the idea of a set of things that
       need to happen together. 
       
       Usually, in a relational database, 
       one unit of work == one database transaction."""
       
    def __init__(self, sessionfactory):
        self.sessionfactory = sessionfactory

    def __enter__(self):
        self.session = self.sessionfactory()
        return self

    def __exit__(self, type, value, traceback):
        self.session.close()

    def commit(self):
        self.session.commit()

    def rollback(self):
        self.session.rollback()

    # I tend to put my repositories onto my UOW
    # for convenient access. 
    @property
    def issues(self):
        return IssueRepository(self.session)
```

This code is taken from a current production system - the code to implement
these patterns really isn't complex. The only thing missing here is some logging
and error handling in the commit method. Our unit-of-work manager creates a new
unit-of-work, or gives us an existing one depending on how we've configured
SqlAlchemy. The unit of work itself is just a thin layer over the top of
SqlAlchemy that gives us explicit rollback and commit points. Let's revisit our
first command handler and see how we might use these patterns together.

```python
class ReportIssueHandler:
    def __init__(self, uowm:UnitOfWorkManager):
        self.uowm = uowm
        
    def handle(self, cmd):
        with self.uowm.start() as unit_of_work:
            reporter = IssueReporter(cmd.reporter_name, cmd.reporter_email)
            issue = Issue(reporter, cmd.problem_description)
            unit_of_work.issues.add(issue)
            unit_of_work.commit()
```

Our command handler looks more or less the same, except that it's now
responsible for starting a unit-of-work, and committing the unit-of-work when it
has finished. This is in keeping with our rule #1 - we will clearly define the
beginning and end of use cases. We know for a fact that only one object is being
loaded and modified here, and our database transaction is kept short. Our
handler depends on an abstraction - the UnitOfWorkManager, and doesn't care if
that's a test-double or a SqlAlchemy session, so that's rule #2 covered. Lastly,
this code is painfully  boring because it's just glue. We're moving all the dull
glue out to the edges of our system so that we can write our domain model in any
way that we like: rule #3 observed.

The code sample for this part
[https://github.com/bobthemighty/blog-code-samples/tree/master/ports-and-adapters/02] 
 adds a couple of new packages - one for slow tests
[http://pycon-2012-notes.readthedocs.io/en/latest/fast_tests_slow_tests.html] 
(tests that go over a network, or to a real file system), and one for our
adapters. We haven't added any new features yet, but we've added a test that
shows we can insert an Issue into a sqlite database through our command handler
and unit of work. Notice that all of the ORM code is in one module
(issues.adapters.orm) and that it depends on our domain model, not the other way
around. Our domain objects don't inherit from SqlAlchemy's declarative base.
We're beginning to get some sense of what it means to have the domain on the
"inside" of a system, and the infrastructural code on the outside.

Our unit test has been updated to use a unit of work, and we can now test that
we insert an issue into our issue log, and commit the unit of work, without
having a dependency on any actual implementation details. We could completely
delete SqlAlchemy from our code base, and our unit tests would continue to work,
because we have a pure domain model and we expose abstract ports from our
service layer.

```python
class When_reporting_an_issue:

    def given_an_empty_unit_of_work(self):
        self.uow = FakeUnitOfWork()

    def because_we_report_a_new_issue(self):
        handler = ReportIssueHandler(self.uow)
        cmd = ReportIssueCommand(name, email, desc)

        handler.handle(cmd)

    def the_handler_should_have_created_a_new_issue(self):
        expect(self.uow.issues).to(have_len(1))

    def it_should_have_recorded_the_issuer(self):
        expect(self.uow.issues[0].reporter.name).to(equal(name))
        expect(self.uow.issues[0].reporter.email).to(equal(email))

    def it_should_have_recorded_the_description(self):
        expect(self.uow.issues[0].description).to(equal(desc))

    def it_should_have_committed_the_unit_of_work(self):
        expect(self.uow.was_committed).to(be_true)
```

Next time [https://io.made.com/blog/commands-and-queries-handlers-and-views] 
we'll look at how to get data back out of the system.
