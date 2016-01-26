//服务创建
function service_create(tenantName, service_key) {
	window.location.href = "/apps/" + tenantName
			+ "/service-deploy/?service_key=" + service_key
}
//创建应用
$(function(){
    $('#create_service_name').blur(function(){
        var appName = $(this).val(),
            checkReg = /^[a-z][a-z0-9-]*[a-z0-9]$/,
            result = true;
            
        if(!checkReg.test(appName)){
            $('#create_service_notice').slideDown();
            return;
        }else{
            $('#create_service_notice').slideUp();
        }
    });
    //第一步
    $('#back_service_step1').click(function(){
        var appName = $('#create_service_name').val(),
            checkReg = /^[a-z][a-z0-9-]*[a-z0-9]$/,
            result = true;
            
        if(!checkReg.test(appName)){
            $('#create_service_notice').slideDown();
            return;
        }else{
            $('#create_service_notice').slideUp();
        }        
        /*var service_dependecy = $("#service_dependecy").val()        
		if(service_dependecy !=""){
			var _selectValue = $('input[type="radio"][name="delineCheckbox1"]:checked').val()
			if (typeof(_selectValue) != "undefined") { 
				var str = _selectValue.split("_");
				if(str[0] == service_dependecy){
					$("#createService").val(str[0])
					$("#hasService").val("")
				}else{
					$("#hasService").val(str[0])
					$("#createService").val("")
				}
			}			
			var createService = $("#createService").val()
			var hasService = $('#hasService').val()
			
			if(createService=="" && hasService==""){
				$('#create_dependency_service_notice').slideDown();
				return;
			}
		}*/
		var tenantName = $("#tenantName").val()
		$("#back_service_step1").prop('disabled', true)
		var _data = $("form").serialize();
    	$.ajax({
    		type : "post",
    		url : "/apps/" + tenantName + "/service-deploy/",
    		data : _data,
    		cache : false,
    		beforeSend : function(xhr, settings) {
    			var csrftoken = $.cookie('csrftoken');
    			xhr.setRequestHeader("X-CSRFToken", csrftoken);
    		},
    		success : function(msg) {
    			var dataObj = msg;
    			if (dataObj["status"] == "notexist"){
    				swal("所选的服务类型不存在");
    			} else if (dataObj["status"] == "owed"){
    				swal("余额不足请及时充值")
    			} else if (dataObj["status"] == "exist") {
    				swal("服务名已存在");
    			} else if (dataObj["status"] == "over_memory") {
    				swal("免费资源已达上限，不能创建");
    			} else if (dataObj["status"] == "over_money") {
    				swal("余额不足，不能创建");
    			} else if (dataObj["status"] == "empty") {
    				swal("服务名称不能为空");    				
    			}else if (dataObj["status"] == "success") {
    				service_alias = dataObj["service_alias"]
    				window.location.href = "/apps/" + tenantName + "/" + service_alias + "/setup/extra/";
    			} else {
    				swal("创建失败");
    				$("#back_service_finished").prop('disabled', false)
                }
    			$("#back_service_finished").prop('disabled', false)
    		},
    		error : function() {
    			swal("系统异常,请重试");
    			$("#back_service_finished").prop('disabled', false)
    		}
    	})
    });

    $('#back_service_finished').click(function() {
        envs = []
        $('tbody tr').each(function() {
            env = {};
            $(this).find('[name^=attr]').each(function(event) {
                i = $(this);
                name = $(this).attr('name');
                value = $(this).val() || i.html();
                if (value) {
                    env[name] = value;
                } else {
                    showMessage("有未填写的内容");
                    return;
                }
            });
            envs.push(env);
        });
        var csrftoken = $.cookie('csrftoken');
        data = {"envs": envs};
        $.ajax({
          url: window.location.pathname,
          method: "POST",
          data: $.stringify(data),
          beforeSend: function(xhr) {
            xhr.setRequestHeader("X-CSRFToken", csrftoken);
          },
          success :function (event) {
            if (event.success) {
              window.location.href = event.next_url;
            } else {
              showMessage(event.info);
            }
          },
          contentType: 'application/json; charset=utf-8',

          statusCode: {
            403: function(event) {
              alert("你没有此权限");
            }
          },
        });
    });
});