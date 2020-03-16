title: Introducing Command Handler
author: Bob

---

The term DDD comes from the book by Eric Evans: ["Domain-Driven Design: Tackling
Complexity in the Heart of Software"]([https://www.amazon.co.uk/Domain-driven-Design-Tackling-Complexity-Software/dp/0321125215).
In his book he describes a set of practices that aim to help us build
maintainable, rich, software systems that solve customer's problems. The book is
560 pages of dense insight, so you'll pardon me if my summary elides some
details, but in brief he suggests:

 * Listen very carefully to your domain experts - the people whose job you're
   automating or assisting in software.
 * Learn the jargon that they use, and help them to come up with new jargon, so
   that every concept in their mental model is named by a single precise term.
 * Use those terms to model your software; the nouns and verbs of the domain
   expert are the classes and methods you should use in modelling.
 * Whenever there is a discrepancy between your shared understanding of the
   domain, go and talk to the domain experts again, and then refactor
   aggressively.

This sounds great in theory, but in practice we often find that our business
logic escapes from our model objects; we end up with logic bleeding into
controllers, or into fat "manager" classes. We find that refactoring becomes
difficult: we can't split a large and important class, because that would
seriously impact the database schema; or we can't rewrite the internals of an
algorithm because it has become tightly coupled to code that exists for a
different use-case. The good news is that these problems can be avoided, since
they are caused by a lack of organisation in the codebase. In fact, the tools to
solve these problems take up half of the DDD book, but it can be be difficult to
understand how to use them together in the context of a complete system.

I want to use this series to introduce an architectural style called
[Ports and Adapters](http://wiki.c2.com/?PortsAndAdaptersArchitecture),
and a design pattern named
[Command Handler](https://matthiasnoback.nl/2015/01/responsibilities-of-the-command-bus/).
I'll be explaining the patterns in Python because that's the language that I use
day-to-day, but the concepts are applicable to any OO language, and can be
massaged to work perfectly in a functional context. There might be a lot more
layering and abstraction than you're used to, especially if you're coming from a
Django background or similar, but please bear with me. In exchange for a more
complex system at the outset, we can avoid much of our [accidental complexity](http://wiki.c2.com/?AccidentalComplexity)  later.

The system we're going to build is an issue management system, for use by a
helpdesk. We're going to be replacing an existing system, which consists of an
HTML form that sends an email. The emails go into a mailbox, and helpdesk staff
go through the mails triaging problems and picking up problems that they can
solve. Sometimes issues get overlooked for a long time, and the helpdesk team
have invented a complex system of post-it notes and whiteboard layouts to track
work in progress. For a while this system has worked pretty well but, as the
system gets busier, the cracks are beginning to show.

Our first conversation with the domain expert
"What's the first step in the process?" you ask, "How do tickets end up in the
mail box?".

"Well, the first thing that happens is the user goes to the web page, and they
fill out some details, and report an issue. That sends an email into the issue
log and then we pick issues from the log each morning".

"So when a user reports an issue, what's the minimal set of data that you need
from them?"

"We need to know who they are, so their name, and email I guess. Uh... and the
problem description. They're supposed to add a category, but they never do, and
we used to have a priority, but everyone set their issue to EXTREMELY URGENT, so
it was useless.

"But a category and priority would help you to triage things?"

"Yes, that would be really helpful if we could get users to set them properly."

This gives us our first use case: As a user, I want to be able to report a new
issue.

Okay, before we get to the code, let's talk about architecture. The architecture
of a software system is the overall structure - the choice of language,
technology, and design patterns that organise the code and satisfy our
constraints [https://en.wikipedia.org/wiki/Non-functional_requirement]. For our
architecture, we're going to try and stick with three principles:

 1. We will always define where our use-cases begin and end. We won't have
    business processes that are strewn all over the codebase.
 2. We will depend on abstractions
    [https://en.wikipedia.org/wiki/Dependency_inversion_principle], and not on
    concrete implementations.
 3. We will treat glue code as distinct from business logic, and put it in an
    appropriate place.

Firstly we start with the domain model. The domain model encapsulates our shared
understanding of the problem, and uses the terms we agreed with the domain
experts. In keeping with principle #2 we will define abstractions for any
infrastructural or technical concerns and use those in our model. For example,
if we need to send an email, or save an entity to a database, we will do so
through an abstraction that captures our intent. In this series we'll create a
separate python package for our domain model so that we can be sure it has no
dependencies on the other layers of the system. Maintaining this rule strictly
will make it easier to test and refactor our system, since our domain models
aren't tangled up with messy details of databases and http calls.



Around the outside of our domain model we place services. These are stateless
objects that do stuff to the domain. In particular, for this system, our command
handlers are part of the service layer.



Finally, we have our adapter layer. This layer contains code that drives the
service layer, or provides services to the domain model. For example, our domain
model may have an abstraction for talking to the database, but the adapter layer
provides a concrete implementation. Other adapters might include a Flask API, or
our set of unit tests, or a celery event queue. All of these adapters connect
our application to the outside world.



In keeping with our first principle, we're going to define a boundary for this
use case and create our first Command Handler. A command handler is an object
that orchestrates a business process. It does the boring work of fetching the
right objects, and invoking the right methods on them. It's similar to the
concept of a Controller in an MVC architecture.

First, we create a Command object.

```python
class ReportIssueCommand(NamedTuple):
        reporter_name: str
        reporter_email: str
        problem_description: str
```

A command object is a small object that represents a state-changing action that
can happen in the system. Commands have no behaviour, they're pure data
structures. There's no reason why you have to represent them with classes, since
all they need is a name and a bag of data, but a NamedTuple is a nice compromise
between simplicity and convenience. Commands are instructions from an external
agent (a user, a cron job, another service etc.) and have names in the
imperative tense, for example:

 * ReportIssue
 * PrepareUploadUri
 * CancelOutstandingOrders
 * RemoveItemFromCart
 * OpenLoginSession
 * PlaceCustomerOrder
 * BeginPaymentProcess

We should try  to avoid the verbs Create, Update, or Delete (and their synonyms)
because those are technical implementations. When we listen to our domain
experts, we often find that there is a better word for the operation we're
trying to model. If all of your commands are named "CreateIssue", "UpdateCart",
"DeleteOrders", then you're probably not paying enough attention to the language
that your stakeholders are using.

The command objects belong to the domain, and they express the API of your
domain. If every state-changing action is performed via a command handler, then
the list of Commands is the complete list of supported operations in your domain
model. This has two major benefits:

 1. If the only way to change state in the system is through a command, then the
    list of commands tells me all the things I need to test. There are no other
    code paths that can modify data.
 2. Because our commands are lightweight, logic-free objects, we can create them
    from an HTTP post, or a celery task, or a command line csv reader, or a unit
    test. They form a simple and stable API for our system that does not depend
    on any implementation details and can be invoked in multiple ways.

In order to process our new command, we'll need to create a command handler.

```python
class ReportIssueCommandHandler:
    def __init__(self, issue_log):
        self.issue_log = issue_log

    def __call__(self, cmd):
        reported_by = IssueReporter(
            cmd.reporter_name,
            cmd.reporter_email)
        issue = Issue(reported_by, cmd.problem_description)
        self.issue_log.add(issue)
```


Command handlers are stateless objects that orchestrate the behaviour of a
system. They are a kind of glue code, and manage the boring work of fetching and
saving objects, and then notifying other parts of the system. In keeping with
principle #3, we keep this in a separate layer. To satisfy principle #1, each
use case is a separate command handler and has a clearly defined beginning and
end. Every command is handled by exactly one  command handler.

In general all command handlers will have the same structure:

 1. Fetch the current state from our persistent storage.
 2. Update the current state.
 3. Persist the new state.
 4. Notify any external systems that our state has changed.

We will usually avoid if statements, loops, and other such wizardry in our
handlers, and stick to a single possible line of execution. Command handlers are
 boring  glue code.
Since our command handlers are just glue code, we won't put any business logic
into them - they shouldn't be making any business decisions. For example, let's
skip ahead a little to a new command handler:

```python
class MarkIssueAsResolvedHandler:
    def __init__(self, issue_log):
        self.issue_log = issue_log

    def __call__(self, cmd):
        issue = self.issue_log.get(cmd.issue_id)
        # the following line encodes a business rule
        if (issue.state != IssueStatus.Resolved):
            issue.mark_as_resolved(cmd.resolution)
```

This handler violates our glue-code principle because it encodes a business
rule: "If an issue is already resolved, then it can't be resolved a second
time". This rule belongs in our domain model, probably in the mark_as_resolved
method of our Issue object.
I tend to use classes for my command handlers, and to invoke them with the call
magic method, but a function is perfectly valid as a handler, too. The major
reason to prefer a class is that it can make dependency management a little
easier, but the two approaches are completely equivalent. For example, we could
rewrite our ReportIssueHandler like this:

```python
def ReportIssue(issue_log, cmd):
    reported_by = IssueReporter(
        cmd.reporter_name,
        cmd.reporter_email)
    issue = Issue(reported_by, cmd.problem_description)
    issue_log.add(issue)
```

If magic methods make you feel queasy, you can define a handler to be a class
that exposes a handle method like this:

```python
class ReportIssueHandler:
    def handle(self, cmd):
       ...
```

However you structure them, the important ideas of commands and handlers are:

 1. Commands are logic-free data structures with a name and a bunch of values.
 2. They form a stable, simple API that describes what our system can do, and
    doesn't depend on any implementation details.
 3. Each command can be handled by exactly one handler.
 4. Each command instructs the system to run through one use case.
 5. A handler will usually do the following steps: get state, change state,
    persist state, notify other parties that state was changed.

Let's take a look at the complete system, I'm concatenating all the files into a
single code listing for each of grokking, but in the git repository
[https://github.com/bobthemighty/blog-code-samples/tree/master/ports-and-adapters/01]
 I'm splitting the layers of the system into separate packages. In the real
world, I would probably use a single python package for the whole app, but in
other languages - Java, C#, C++ - I would usually have a single binary for each
layer. Splitting the packages up this way makes it easier to understand how the
dependencies work.

```python
from typing import NamedTuple
from expects import expect, have_len, equal

# Domain model

class IssueReporter:
    def __init__(self, name, email):
        self.name = name
        self.email = email


class Issue:
    def __init__(self, reporter, description):
        self.description = description
        self.reporter = reporter


class IssueLog:
    def add(self, issue):
        pass


class ReportIssueCommand(NamedTuple):
    reporter_name: str
    reporter_email: str
    problem_description: str


# Service Layer

class ReportIssueHandler:

    def __init__(self, issue_log):
        self.issue_log = issue_log

    def __call__(self, cmd):
        reported_by = IssueReporter(
            cmd.reporter_name,
            cmd.reporter_email)
        issue = Issue(reported_by, cmd.problem_description)
        self.issue_log.add(issue)


# Adapters

class FakeIssueLog(IssueLog):

    def __init__(self):
        self.issues = []

    def add(self, issue):
        self.issues.append(issue)

    def get(self, id):
        return self.issues[id]

    def __len__(self):
        return len(self.issues)

    def __getitem__(self, idx):
        return self.issues[idx]


email = "bob@example.org"
name = "bob"
desc = "My mouse won't move"


class When_reporting_an_issue:

    def given_an_empty_issue_log(self):
        self.issues = FakeIssueLog()

    def because_we_report_a_new_issue(self):
        handler = ReportIssueHandler(self.issues)
        cmd = ReportIssueCommand(name, email, desc)

        handler(cmd)

    def the_handler_should_have_created_a_new_issue(self):
        expect(self.issues).to(have_len(1))

    def it_should_have_recorded_the_issuer(self):
        expect(self.issues[0].reporter.name).to(equal(name))
        expect(self.issues[0].reporter.email).to(equal(email))

    def it_should_have_recorded_the_description(self):
        expect(self.issues[0].description).to(equal(desc))
```

There's not a lot of functionality here, and our issue log has a couple of
problems, firstly there's no way to see the issues in the log yet, and secondly
we'll lose all of our data every time we restart the process. We'll fix the
second of those in the next part
[https://io.made.com/blog/repository-and-unit-of-work-pattern-in-python/].
