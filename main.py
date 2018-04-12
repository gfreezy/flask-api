import inspect
import sys
import werkzeug
import ujson
import pdb
from functools import wraps
from flask import Flask, request, Response
from pydantic import BaseModel, ValidationError


def jsonify(data, status_code=200):
    return Response(ujson.dumps(data),
                    mimetype='application/json', status=status_code)


def ok(content=''):
    msg = {
        'status': 'ok',
        'content': content,
    }
    return jsonify(msg)


def error(error='', status_code=400):
    if isinstance(error, (tuple, list)):
        msg = {
            'status': 'error',
            'code': error[0],
            'msg': error[1],
        }
    else:
        msg = {
            'status': 'error',
            'msg': error,
        }

    resp = jsonify(msg, status_code=status_code)
    return resp


def field_doc(field):
    if issubclass(field.type_, BaseModel):
        return model_doc(field.type_)
    return field.info


def model_doc(model: BaseModel):
    return {
        'type': model.__name__,
        'fields': [{'name': name, **field_doc(f)} for name, f in model.__fields__.items()]
    }


def view_doc(rule, view_func):
    doc = {
        'rule': rule,
        'description': view_func.__doc__,
        'parameters': [],
        'return': None
    }

    sig = inspect.signature(view_func, follow_wrapped=True)
    for k, v in sig.parameters.items():
        doc['parameters'].append({
            'name': k,
            **model_doc(v.annotation)
        })

    if issubclass(sig.return_annotation, BaseModel):
        doc['return'] = model_doc(sig.return_annotation)

    return doc


def app_doc(app):
    doc = {
        'name': app.name,
        'endpoints': []
    }
    for rule in app.url_map.iter_rules():
        view_func = app.view_functions[rule.endpoint]
        if getattr(view_func, 'is_custom', False):
            doc['endpoints'].append(view_doc(rule.rule, view_func))

    return doc
        

class Req(BaseModel):
    id: int
    name: str


class Resp(BaseModel):
    reply: str
    req: Req


class App(Flask):
    def rpc_route(self, rule, **options):
        orig_decorator = super().route(rule, methods=['POST', 'GET'], **options)

        def decorator(f):
            sig = inspect.signature(f, follow_wrapped=True)
            ReqType = list(sig.parameters.values())[0].annotation if sig.parameters else None

            @wraps(f)
            def _(*args, **kwargs):
                try:
                    if ReqType:
                        d = request.get_json(force=True)
                        j = ReqType.parse_obj(d)
                        return ok(f(j).dict())
                    else:
                        return ok(f().dict())
                except ValidationError as e:
                    return error(str(e))

            _.is_custom = True
            return orig_decorator(_)

        return decorator

    def rpc(self, f):
        return self.rpc_route(f'/{f.__name__}.json')(f)


app = App('typing')


@app.rpc
def index(req: Req) -> Resp:
    """index"""
    return Resp(reply="1")


@app.rpc_route('/ddd')
def doc() -> Resp:
    """doc"""
    return Resp(reply="1")


def main():
    print(ujson.dumps(app_doc(app), indent=2))
    app.run(debug=True)


if __name__ == '__main__':
    main()
